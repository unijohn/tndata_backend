"""Models for the Goals app.

This is our collection of Goals & Behaviors. They're organized as follows:

    [Category] <-> [Goal] <-> [Behavior] <- [Action]

Actions are the things we want to help people to do.

"""
import hashlib
import os
import pytz

from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.db import connection, models
from django.db.models import Avg, Sum, ObjectDoesNotExist
from django.db.models.signals import (
    pre_delete, pre_save, post_delete, post_save
)
from django.dispatch import receiver
from django.utils.text import slugify
from django.utils import timezone

from dateutil.relativedelta import relativedelta
from django_fsm import FSMField, transition
from jsonfield import JSONField
from markdown import markdown
from notifications.models import GCMMessage
from notifications.signals import notification_snoozed
from recurrence import serialize as serialize_recurrences
from recurrence.fields import RecurrenceField
from redis_metrics import metric
from utils import colors, dateutils
from utils.user_utils import local_day_range, to_localtime, to_utc, user_timezone

from .encoder import dump_kwargs
from .managers import (
    CategoryManager,
    GoalManager,
    PackageEnrollmentManager,
    TriggerManager,
    UserActionManager,
    UserBehaviorManager,
    UserCategoryManager,
    UserGoalManager,
    WorkflowManager
)
from .mixins import ModifiedMixin, StateMixin, UniqueTitleMixin, URLMixin
from .utils import clean_title, clean_notification, strip


def _custom_triggers_allowed(user, user_object, timeout=90):
    """This function looks up all of a user's selected content IDs, storing
    them in a dict keyed by an object type. The idea is to check all of these
    against the user's Packages at once (which is expensive) and cache this
    for a period.

    That way we don't have to perform this operation for every UserCategory,
    UserGoal, UserBehavior, UserAction selected by the user during serialization.

    """
    object_type = user_object.__class__.__name__.lower()
    cache_key = 'restricted-user-objects-{}'.format(user.id)
    restricted = cache.get(cache_key)
    if restricted is None:
        # All the packages with restricted triggers
        packages = user.packageenrollment_set.filter(prevent_custom_triggers=True)
        restricted_categories = packages.values_list('category_id', flat=True)
        restricted_goals = packages.values_list('goals__id', flat=True)

        # List of UserCategopry IDs that don't allow custom triggers
        qs = user.usercategory_set.filter(category__id__in=restricted_categories)
        restricted_user_categories = qs.values_list('id', flat=True)

        # List of UserGoal IDs that don't allow custom triggers
        qs = user.usergoal_set.filter(goal__id__in=restricted_goals)
        restricted_user_goals = qs.values_list('id', flat=True)

        # List of UserBehavior IDs that don't allow custom triggers
        qs = user.userbehavior_set.filter(behavior__goals__id__in=restricted_goals)
        restricted_user_behaviors = qs.values_list('id', flat=True)

        # List of UserAction IDs that don't allow custom triggers
        qs = user.useraction_set.filter(action__behavior__goals__id__in=restricted_goals)
        restricted_user_actions = qs.values_list('id', flat=True)

        restricted = {
            'usercategory': restricted_user_categories,
            'usergoal': restricted_user_goals,
            'userbehavior': restricted_user_behaviors,
            'useraction': restricted_user_actions,
        }
        cache.set(cache_key, restricted, timeout=timeout)
    return user_object.id not in restricted[object_type]


def _upload_path(path_format, instance, filename):
    """Create an upload path (including a filename) for an uploaded file.

    * path_format: A format string for some object type. It should have accept
      one paramter: e.g. "/path/{}/dir/".
    * instance: the instance of the model containing a FileField or ImageField.
    * filename: original filename of the file.

    This function will create a new filename that is a hash of the original and
    the current time. Uploaded files whill always have a new filename.

    """
    original_filename, ext = os.path.splitext(filename)
    hash_content = "{}-{}".format(filename, timezone.now().strftime("%s"))
    filename = hashlib.md5(hash_content.encode("utf8")).hexdigest()
    if ext:
        filename += ext
    path = path_format.format(type(instance).__name__.lower())
    return os.path.join(path, filename)


def _category_icon_path(instance, filename):
    return _upload_path("goals/{}", instance, filename)


def _catetgory_image_path(instance, filename):
    return _upload_path("goals/{}/images", instance, filename)


class Category(ModifiedMixin, StateMixin, UniqueTitleMixin, URLMixin, models.Model):
    """A Broad grouping of possible Goals from which users can choose.

    We also have content (goals, behaviors, actions) that is associated with
    a single organization. We've been referring to this scenario as "packaged
    content", and in this case a Category serves as the Organization's content
    "container".

    """
    DEFAULT_PRIMARY_COLOR = "#2E7D32"
    DEFAULT_SECONDARY_COLOR = "#4CAF50"

    # URLMixin attributes
    urls_app_namespace = "goals"
    urls_fields = ['pk', 'title_slug']
    urls_model_name = "category"
    urls_icon_field = "icon"
    urls_image_field = "image"

    # Data Fields. Relevant to all Categories (public and packaged)
    order = models.PositiveIntegerField(
        unique=True,
        help_text="Controls the order in which Categories are displayed."
    )
    title = models.CharField(
        max_length=128,
        db_index=True,
        unique=True,
        help_text="A Title for the Category (50 characters)"
    )
    title_slug = models.SlugField(max_length=128, db_index=True, unique=True)
    description = models.TextField(
        help_text="A short (250 character) description for this Category"
    )
    icon = models.ImageField(
        upload_to=_category_icon_path,
        null=True,
        blank=True,
        help_text="Upload a square icon to be displayed for the Category."
    )
    image = models.ImageField(
        upload_to=_catetgory_image_path,
        null=True,
        blank=True,
        help_text="A Hero image to be displayed at the top of the Category pager"
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Additional notes regarding this Category"
    )
    color = models.CharField(
        max_length=7,
        default=DEFAULT_PRIMARY_COLOR,
        help_text="Select the color for this Category"
    )
    secondary_color = models.CharField(
        max_length=7,
        blank=True,
        default=DEFAULT_SECONDARY_COLOR,
        help_text="Select a secondary color for this Category. If omitted, a "
                  "complementary color will be generated."
    )
    state = FSMField(default="draft")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="categories_updated",
        null=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="categories_created",
        null=True
    )

    # Fields related to 'Packaged Content'
    packaged_content = models.BooleanField(
        default=False,
        help_text="Is this Category for a collection of packaged content?"
    )
    package_contributors = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="packagecontributor_set",
        help_text="The group of users that will contribute to content in "
                  "this category."
    )

    # Packaged content has a consent form (for now anyway). These are only
    # used if a category is marked as a package, and are only available for
    # editing in packages. Both of these should allow markdown.
    consent_summary = models.TextField(blank=True)
    consent_more = models.TextField(blank=True)
    prevent_custom_triggers_default = models.BooleanField(
        default=False,
        help_text="This option determines whether or not custom triggers will "
                  "be allowed by default when enrolling users in the package."
    )
    display_prevent_custom_triggers_option = models.BooleanField(
        default=True,
        help_text="This option determines whether or not package contributors "
                  "will see the option to prevent custom triggers during "
                  "user enrollment."
    )

    # timestamps
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['order', 'title']
        verbose_name = "Category"
        verbose_name_plural = "Categories"
        # add_category, change_category, delete_category are created by default.
        permissions = (
            ("view_category", "Can view Categories"),
            ("decline_category", "Can Decline Categories"),
            ("publish_category", "Can Publish Categories"),
        )

    @property
    def is_packaged(self):
        return self.packaged_content

    @property
    def rendered_description(self):
        """Render the description markdown"""
        return markdown(self.description)

    @property
    def rendered_consent_summary(self):
        """Render the consent_summary markdown"""
        return markdown(self.consent_summary)

    @property
    def rendered_consent_more(self):
        """Render the consent_more markdown"""
        return markdown(self.consent_more)

    @property
    def goals(self):
        """This property returns a QuerySet of the related Goal objects."""
        return self.goal_set.all().distinct()

    @property
    def behaviors(self):
        """Returns a QuerySet of all Behaviors nested beneath this category's
        set of goals."""
        ids = self.goals.values_list('behavior', flat=True)
        return Behavior.objects.filter(pk__in=ids)

    @property
    def actions(self):
        """Returns a QuerySet of all Actions nested beneath this category's
        set of Goals & Behaviors. """
        ids = self.behaviors.values_list('action', flat=True)
        return Action.objects.filter(pk__in=ids)

    def _format_color(self, color):
        """Ensure that colors include a # symbol at the beginning."""
        return color if color.startswith("#") else "#{0}".format(color)

    def _generate_secondary_color(self):
        if self.secondary_color:
            return self.secondary_color
        else:
            return colors.lighten(self.color)

    def save(self, *args, **kwargs):
        """Always slugify the name prior to saving the model and set
        created_by or updated_by fields if specified."""
        self.title_slug = slugify(self.title)
        self.color = self._format_color(self.color)
        self.secondary_color = self._generate_secondary_color()
        kwargs = self._check_updated_or_created_by(**kwargs)
        super(Category, self).save(*args, **kwargs)

    @transition(field=state, source="*", target='draft')
    def draft(self):
        pass

    @transition(field=state, source=["draft", "declined"], target='pending-review')
    def review(self):
        pass

    @transition(field=state, source="pending-review", target='declined')
    def decline(self):
        pass

    @transition(field=state, source=["draft", "pending-review"], target='published')
    def publish(self):
        pass

    def get_view_enrollment_url(self):
        """Essentially a Detail view for a Category Package."""
        return reverse("goals:package-detail", args=[self.id])

    def get_enroll_url(self):
        return reverse("goals:package-enroll", args=[self.id])

    def get_package_calendar_url(self):
        if self.packaged_content:
            return reverse("goals:package-calendar", args=[self.id])

    objects = CategoryManager()


def _goal_icon_path(instance, filename):
    return _upload_path("goals/{}", instance, filename)


class Goal(ModifiedMixin, StateMixin, UniqueTitleMixin, URLMixin, models.Model):

    # URLMixin attributes
    urls_app_namespace = "goals"
    urls_fields = ['pk', 'title_slug']
    urls_model_name = "goal"
    urls_icon_field = "icon"

    # Data Fields
    categories = models.ManyToManyField(
        Category,
        blank=True,
        help_text="Select the Categories in which this Goal should appear."
    )
    title_slug = models.SlugField(max_length=256, null=True)
    title = models.CharField(
        max_length=256, db_index=True, unique=True,
        help_text="A Title for the Goal (50 characters)"
    )
    subtitle = models.CharField(
        max_length=256,
        null=True,
        help_text="A one-liner description for this goal."
    )
    description = models.TextField(
        blank=True,
        help_text="A short (250 character) description for this Goal"
    )
    outcome = models.TextField(
        blank=True,
        help_text="Desired outcome of this Goal."
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Misc notes about this item. This is for your use and will "
                  "not be displayed in the app."
    )
    more_info = models.TextField(
        blank=True,
        help_text="Optional tips and tricks or other small, associated ideas. "
                  "Consider using bullets."
    )
    icon = models.ImageField(
        upload_to=_goal_icon_path,
        null=True,
        blank=True,
        help_text="Upload an icon (256x256) for this goal"
    )
    state = FSMField(default="draft")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="goals_updated",
        null=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="goals_created",
        null=True
    )
    keywords = ArrayField(
        models.CharField(max_length=32, blank=True),
        default=list,
        blank=True,
        help_text="Add keywords for this goal. These will be used to generate "
                  "suggestions for the user."
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "{0}".format(self.title)

    class Meta:
        ordering = ['title']
        verbose_name = "Goal"
        verbose_name_plural = "Goals"
        # add_goal, change_goal, delete_goal are created by default.
        permissions = (
            ("view_goal", "Can view Goals"),
            ("decline_goal", "Can Decline Goals"),
            ("publish_goal", "Can Publish Goals"),
        )

    def _clean_keywords(self):
        """Split keywords on spaces, lowercase, and strip whitespace."""
        keywords = " ".join(self.keywords).lower()
        self.keywords = [kw.strip() for kw in keywords.split()]

    def get_async_icon_upload_url(self):
        return reverse("goals:file-upload", args=["goal", self.id])

    @property
    def rendered_description(self):
        """Render the description markdown"""
        return markdown(self.description)

    def save(self, *args, **kwargs):
        """This method ensurse we always perform a few tasks prior to saving
        a Goal. These include:

        - Always slugify the title.
        - Always clean keywords (strip & lowercase)
        - Set the updated_by/created_by fields when possible.

        """
        self.title_slug = slugify(self.title)
        self._clean_keywords()
        kwargs = self._check_updated_or_created_by(**kwargs)
        super(Goal, self).save(*args, **kwargs)

    @transition(field=state, source="*", target='draft')
    def draft(self):
        pass

    @transition(field=state, source=["draft", "declined"], target='pending-review')
    def review(self):
        pass

    @transition(field=state, source="pending-review", target='declined')
    def decline(self):
        pass

    @transition(field=state, source=["draft", "pending-review"], target='published')
    def publish(self):
        pass

    def get_parent_category_for_user(self, user):
        """Return one of this object's parent categories, prefering one that
        the given user has selected.

        * user - A User instance. We return a Category that the user has
          selected if possible.

        """
        user_cats = user.usercategory_set.values_list('category', flat=True)
        cat = self.categories.filter(id__in=user_cats).first()
        if cat is None:
            cat = self.categories.first()
        return cat

    objects = GoalManager()


class Trigger(models.Model):
    """Definition for a (possibly recurring) reminder for an user's Actions.

    A Trigger consists of one or more of the following:

    - A date and/or time when a notification should be sent.
    - Recurrences: How frequently (every day, once a month, etc) should the
      notification be sent.
    - Whether or not trigger should stop once the action has been completed.

    This model is heavily based on django-recurrence:
    https://django-recurrence.readthedocs.org

    """
    RELATIVE_UNIT_CHOICES = (
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months'),
        ('years', 'Years'),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        help_text="A Custom trigger, created by a user."
    )
    name = models.CharField(
        max_length=128,
        db_index=True,
        help_text="A human-friendly name for this trigger"
    )
    name_slug = models.SlugField(max_length=128, db_index=True)
    time = models.TimeField(
        blank=True,
        null=True,
        help_text="Time the trigger/notification will fire, in 24-hour format."
    )
    trigger_date = models.DateField(
        blank=True,
        null=True,
        help_text="A starting date for a recurrence, or a single date for a "
                  "one-time trigger."
    )
    recurrences = RecurrenceField(
        null=True,
        blank=True,
        help_text="An iCalendar (rfc2445) recurrence rule (an RRULE)"
    )
    start_when_selected = models.BooleanField(
        default=False,
        help_text="Should this trigger start on the day the user selects the "
                  "action? "
    )
    stop_on_complete = models.BooleanField(
        default=False,
        help_text="Should reminders stop after the action has been completed?"
    )
    # Relative reminders examples:
    #
    # - 1 day after action selected
    # - 2 weeks after action selected
    # - 1 year after action selected
    #
    # IDEA: Once a user selects an action with a 'relative' reminder, we
    # immediately turn it into a custom reminder and pre-fill the `trigger_date`
    # based on when the UserAction instance is created. This will require
    # that the newly created UserAction instance know how to modify the trigger
    # accordingly. See the create_relative_reminder signal handler for UserAction
    relative_value = models.IntegerField(default=0)
    relative_units = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        choices=RELATIVE_UNIT_CHOICES,
    )

    # TODO: Add support for recurrences of the form: repeat until occurs x times
    #       AFTER the user selects an action.
    #
    # - requires some flag to opt into that
    # - involves setting the `trigger_date` automatically when the user selects
    #   the action (like we do with other relative reminders)
    # - Needs tests, first?

    def __str__(self):
        return self.name if self.name else "Unnamed Trigger"

    class Meta:
        ordering = ['name', 'id']
        verbose_name = "Trigger"
        verbose_name_plural = "Triggers"
        permissions = (
            ("view_trigger", "Can view Triggers"),
            ("decline_trigger", "Can Decline Triggers"),
            ("publish_trigger", "Can Publish Triggers"),
        )

    def _localize_time(self):
        """Adds the UTC timezone info to self.time."""
        if self.time and self.time.tzinfo is None:
            self.time = pytz.utc.localize(self.time)

    def _strip_rdate_data(self):
        """Our android recurrence dialog doesn't like RDATE rules as part of
        the recurrence; Additionally, we've saved that information as a separate
        field within this model, so let's strip out any RDATE rules.

        """
        rrule = self.serialized_recurrences()
        if rrule and 'RDATE:' in rrule:
            self.recurrences = rrule.split('RDATE:')[0].strip()

    def get_absolute_url(self):
        return reverse('goals:trigger-detail', args=[self.pk])

    def save(self, *args, **kwargs):
        """Always slugify the name prior to saving the model."""
        self.name_slug = slugify(self.name)
        self._localize_time()
        self._strip_rdate_data()
        super(Trigger, self).save(*args, **kwargs)

    @property
    def is_relative(self):
        return (
            self.start_when_selected or
            all([self.relative_units, self.relative_value])
        )

    def relative_trigger_date(self, dt):
        """If this is a custom (has a user), relative trigger (has both a
        relative_value and relative_units or is a `start_when_selected` trigger),
        this method will calculate the trigger_date (when this trigger should
        start) relative to the given datetime object.

        Returns a datetime object or None.

        """
        if self.user and self.is_relative and self.relative_units:
            # build kwargs, e.g.: relativedelta(dt, months=5)
            kwargs = {self.relative_units: self.relative_value}
            return dt + relativedelta(**kwargs)
        elif self.user and self.is_relative and self.start_when_selected:
            # If it's just a "start when selected", return the give time.
            return dt
        return None

    def serialized_recurrences(self):
        """Return a rfc2445 formatted unicode string."""
        if self.recurrences:
            return serialize_recurrences(self.recurrences)
        else:
            return None

    def recurrences_as_text(self):
        if self.recurrences:
            result = ''
            rules = []
            # check all the recurrence rules
            for rule in self.recurrences.rrules:
                rules.append(rule.to_text())
            # also check for exclusion rules
            for exrule in self.recurrences.exrules:
                rules.append("Exclusions: {0}".format(exrule.to_text()))
            result = ", ".join(rules)
            if len(self.recurrences.rdates) > 0:
                result += " on "
                result += ", ".join(
                    ["{0}".format(d) for d in self.recurrences.rdates]
                )
            return result
        return ''

    def _combine(self, a_time, a_date=None, tz=None):
        """Combine a date & time into an timezone-aware datetime object.
        If the date is None, the current date (in either utc or the user's
        local time) will be used."""
        if tz is None:
            tz = self.get_tz()

        if a_date is None:
            a_date = timezone.now().astimezone(tz)

        # Ensure our combined date/time has the appropriate timezone
        if timezone.is_aware(a_time) and a_time.tzinfo != tz:
            # the time value here is correct, but should
            # be in the user's timezone.
            a_time = a_time.replace(tzinfo=None)

        dt = datetime.combine(a_date, a_time)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone=tz)
        elif timezone.is_aware(dt) and tz is not None:
            dt = dt.astimezone(tz)

        return dt

    def get_tz(self, user=None):
        """Return a Timezone object for the user; defaults to UTC if no user."""
        user = user or self.user
        if user:
            return pytz.timezone(user_timezone(user))
        return timezone.utc

    def get_alert_time(self, tz=None):
        """Return a datetime object (with appropriate timezone) for the
        starting date/time for this trigger."""
        if tz is None:
            tz = self.get_tz()
        alert_time = None
        if self.trigger_date and self.time:
            alert_time = self._combine(self.time, self.trigger_date, tz)
        elif self.time is not None:
            now = timezone.now().astimezone(tz)
            alert_time = self._combine(self.time, now, tz)
        return alert_time

    def get_occurences(self, begin=None, days=30):
        """Get some dates in this series of reminders."""
        tz = self.get_tz()
        if begin is None:
            begin = self.get_alert_time(tz)  # "today's" alert time.
        end = begin + timedelta(days=days)  # alerts a month in the future
        dates = list(self.recurrences.occurrences(
            dtstart=begin,
            dtend=end
        ))

        # Since the dtstart argument to `occurences` means that we _always_
        # include that date in the list, we now need to filter out any dates
        # that shouldn't occur on given days. This is a dirty hack.
        def _filter_days(d):
            recurrences_text = self.recurrences_as_text().lower()
            dow = d.strftime("%A").lower()
            if recurrences_text.startswith("weekly") and dow not in recurrences_text:
                return False
            return True
        dates = list(filter(_filter_days, dates))

        # IF our recurrences are empty, just keep the first date.
        if self.recurrences_as_text() == '':
            dates = dates[0:1]

        # Return only dates matching "today" or later.
        now = timezone.now().astimezone(tz)
        return list(filter(lambda d: d.date() >= now.date(), dates))

    def _stopped_by_completion(self, user=None):
        """Determine if triggers should stop because the user has completed
        the action associated with this trigger. This is messy, but it:

        - users the given user, falling back to self.user
        - returns False for no user
        - if this is a default trigger, it looks up the UserCompletedAction
          for the Action on which it is defined as a default
        - if this is a custom trigger, it looks up the UserCompletedAction
          for the associated UserAction
        - If it finds a UserCompletedAction with a state of "complete" it
          returns True
        - If it fails any of the above, it returns False

        Returns True if the trigger should stop, False otherwise.
        """
        user = user or self.user
        if user and self.stop_on_complete:  # This only works if we have a user
            try:
                # While it's technically possible that this trigger could be
                # associated with more than one UserAction, it's unlikely,
                ua = user.useraction_set.filter(custom_trigger=self).first()
                if ua is None:  # This may be a default trigger...
                    ua = user.useraction_set.filter(action=self.action_default).first()
                if ua:
                    # Try to get the UserAction associated with the trigger
                    params = {
                        'user': user,
                        'useraction': ua,
                        'action': ua.action,
                        'state': UserCompletedAction.COMPLETED,
                    }
                    return UserCompletedAction.objects.filter(**params).exists()
            except ObjectDoesNotExist:
                pass
        return False

    def next(self, user=None):
        """Generate the next date for this Trigger. For recurring triggers,
        this will return a datetime object for the next time the trigger should
        fire in the user's local time if, this object is associated with a
        user; otherwise, the date will be in UTC.

        """
        if self._stopped_by_completion(user):
            return None

        tz = self.get_tz(user=user)
        alert_on = self.get_alert_time(tz)
        now = timezone.now().astimezone(tz)
        recurrences = self.serialized_recurrences()

        # No recurrences, alert is in the future
        if recurrences is None and alert_on and alert_on > now:
            return alert_on

        # HACK: If we've stacked a number of RRULEs, let's generate a list of
        # dates in the recurrence (30 days out & starting with the current
        # time), then pick the earliest one.
        elif recurrences and "\n" in recurrences:
            # Generate some dates, keeping only the future ones
            dates = [dt for dt in self.get_occurences(begin=now) if dt > now]
            # Then recombine them all with the trigger time. ugh. :(
            dates = [self._combine(self.time, date) for date in dates]
            if len(dates) > 0:
                return dates[0]

        # HACK to make sure the UNTIL recurrences don't sometime keep returning
        # dates after their specified ending (but don't clobber rules that
        # specify a weekly recurrence for set days; these need to use
        # `recurrences.after`
        elif recurrences and "UNTIL" in recurrences and 'BYDAY' not in recurrences:
            yesterday = alert_on - timedelta(days=1)  # yesterday's alert
            tomorrow = now + timedelta(days=1)  # this time tomorrow
            dates = self.recurrences.between(now, tomorrow, dtstart=yesterday)
            if len(dates) > 0:
                return dates[0]
            else:
                return None

        # Return the next value in the recurrence
        elif recurrences and alert_on:
            return self.recurrences.after(
                now,  # The next recurrence after the current time.
                inc=True,  # return the current time if it matches the recurrence.
                dtstart=alert_on  # The alert time.
            )

        # No recurrence or not a time-pased Trigger.
        return None

    def previous(self, user=None, lookback=30):
        """If this trigger is for a recurring event, this method will generate
        the previous instance of the recurrence in the user's timezone;
        otherwise it will return None.

        Returns the time in the user's local timezone (or None)

        """
        user = self.user or user
        if user is None:
            raise AssertionError("Trigger.previous requires a user.")

        if user and self.recurrences is not None and self.time:
            # recurrences only work with naive datetimes,
            # so try to get today's start
            today = local_day_range(user)[0]
            today = today.replace(tzinfo=None)
            start = today - timedelta(days=lookback)

            dates = self.recurrences.between(
                after=start,
                before=today,
                dtstart=start,
            )
            if len(dates):
                dt = max(dates)
                dt = datetime.combine(dt, self.time.replace(tzinfo=None))
                dt = to_localtime(dt, user)
                return dt
        return None

    objects = TriggerManager()


@receiver(post_save, sender=Trigger, dispatch_uid="custom-trigger-updated")
def custom_trigger_updated(sender, instance, created, raw, using, **kwargs):
    """Record metrics when a User updates their custom triggers."""
    if instance.user:
        metric('custom-trigger-updated', category="User Interactions")


@receiver(pre_delete, sender=Trigger, dispatch_uid="trigger-remove-queued-messages")
@receiver(post_save, sender=Trigger, dispatch_uid="trigger-remove-queued-messages")
def remove_queued_messages(sender, instance, *args, **kwargs):
    """If a trigger is updated, we need to remove all currently queued GCM
    Messages that are using the trigger."""
    try:
        instance.action_default.remove_queued_messages()
    except ObjectDoesNotExist:
        pass


def _behavior_icon_path(instance, filename):
    """Return the path for uploaded icons for `Behavior` and `Action` objects."""
    return _upload_path("goals/{}/icons", instance, filename)


def _behavior_img_path(instance, filename):
    """Return the path for uploaded images for `Behavior` and `Action` objects."""
    return _upload_path("goals/{}/images", instance, filename)


class BaseBehavior(ModifiedMixin, StateMixin, models.Model):
    """This abstract base class contains fields that are common to both
    `Behavior` and `Action` models.

    """
    source_link = models.URLField(
        max_length=256,
        blank=True,
        null=True,
        help_text="A link to the source."
    )
    source_notes = models.TextField(
        blank=True,
        help_text="Narrative notes about the source of this item."
    )
    notes = models.TextField(
        blank=True,
        help_text="Misc notes about this item. This is for your use and will "
                  "not be displayed in the app."
    )
    more_info = models.TextField(
        blank=True,
        help_text="Optional tips and tricks or other small, associated ideas. "
                  "Consider using bullets."
    )
    description = models.TextField(
        blank=True,
        help_text="A brief (250 characters) description about this item."
    )
    case = models.TextField(
        blank=True,
        help_text="Brief description of why this is useful."
    )
    outcome = models.TextField(
        blank=True,
        help_text="Brief description of what the user can expect to get by "
                  "adopting the behavior"
    )
    external_resource = models.CharField(
        blank=True,
        max_length=256,
        help_text=("An external resource is something that will help a user "
                   "accomplish a task. It could be a phone number, link to a "
                   "website, link to another app, or GPS coordinates. ")
    )
    external_resource_name = models.CharField(
        blank=True,
        max_length=256,
        help_text=("A human-friendly name for your external resource. This is "
                   "especially helpful for web links.")
    )
    notification_text = models.CharField(
        max_length=256,
        blank=True,
        help_text="Text of the notification (50 characters)"
    )
    icon = models.ImageField(
        upload_to=_behavior_icon_path,
        null=True,
        blank=True,
        help_text="A square icon for this item in the app, preferrably 512x512."
    )
    image = models.ImageField(
        upload_to=_behavior_img_path,
        null=True,
        blank=True,
        help_text="An image to be displayed for this item, preferrably 1024x1024."
    )
    state = FSMField(default="draft")
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return "{0}".format(self.title)

    def _set_notification_text(self):
        if not self.notification_text:
            self.notification_text = self.title

    @property
    def rendered_description(self):
        """Render the description markdown"""
        return markdown(self.description)

    @property
    def rendered_more_info(self):
        """Render the more_info markdown"""
        return markdown(self.more_info)

    def save(self, *args, **kwargs):
        """Always slugify the name prior to saving the model."""
        self.title_slug = slugify(self.title)
        kwargs = self._check_updated_or_created_by(**kwargs)
        self._set_notification_text()
        super(BaseBehavior, self).save(*args, **kwargs)

    @transition(field=state, source="*", target='draft')
    def draft(self):
        pass

    @transition(field=state, source=["draft", "declined"], target='pending-review')
    def review(self):
        pass

    @transition(field=state, source="pending-review", target='declined')
    def decline(self):
        pass

    @transition(field=state, source=["draft", "pending-review"], target='published')
    def publish(self):
        pass


class Behavior(URLMixin, UniqueTitleMixin,  BaseBehavior):
    """A Behavior. Behaviors have many actions associated with them and contain
    several bits of information for a user."""

    # URLMixin attributes
    urls_app_namespace = "goals"
    urls_model_name = "behavior"
    urls_fields = ["pk", "title_slug"]
    urls_icon_field = "icon"
    urls_image_field = "image"

    # Data Fields
    title = models.CharField(
        max_length=256,
        db_index=True,
        unique=True,
        help_text="A unique title for this Behavior (50 characters)"
    )
    title_slug = models.SlugField(max_length=256, db_index=True, unique=True)
    sequence_order = models.IntegerField(
        default=0,
        db_index=True,
        blank=True,
        help_text="Optional ordering for a sequence of behaviors"
    )
    goals = models.ManyToManyField(
        Goal,
        blank=True,
        help_text="Select the Goal(s) that this Behavior achieves."
    )
    informal_list = models.TextField(
        blank=True,
        help_text="Use this section to create a list of specific actions for "
                  "this behavior. This list will be reproduced as a mnemonic "
                  "on the Action entry page"
    )
    default_trigger = models.ForeignKey(
        Trigger,
        blank=True,
        null=True,
        help_text="A trigger/reminder for this behavior"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="behaviors_updated",
        null=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="behaviors_created",
        null=True
    )

    class Meta(BaseBehavior.Meta):
        ordering = ['sequence_order', 'title']
        verbose_name = "Behavior"
        verbose_name_plural = "Behaviors"
        # add_behavior, change_behavior, delete_behavior are created by default.
        permissions = (
            ("view_behavior", "Can view Permissions"),
            ("decline_behavior", "Can Decline Permissions"),
            ("publish_behavior", "Can Publish Permissions"),
        )

    def get_async_icon_upload_url(self):
        return reverse("goals:file-upload", args=["behavior", self.id])

    @property
    def categories(self):
        """Return a QuerySet of Categories for this object's selected Goals"""
        cats = self.goals.values_list('categories', flat=True)
        return Category.objects.filter(pk__in=cats)

    def get_user_mapping(self, user):
        """Return the first UserBehavior object that matches this Behavior and
        the given user. There _should_ only be one of these. Returns None if
        the object is not found.

        Note: This method can be used by other apps that may have a generic
        relationships (e.g. notifications).

        """
        return self.userbehavior_set.filter(user=user, behavior=self).first()

    objects = WorkflowManager()


class Action(URLMixin, BaseBehavior):
    """Actions are things that people do, and are typically the bit of
    information to which a user will set a reminder (e.g. a Trigger).

    Actions can be of different types, i.e.:

    * Starter Step
    * Tiny Version
    * Resource
    * Right now
    * Custom

    """
    STARTER = "starter"
    TINY = "tiny"
    RESOURCE = "resource"
    NOW = "now"
    LATER = "later"
    CUSTOM = "custom"

    ACTION_TYPE_CHOICES = (
        (STARTER, 'Starter Step'),
        (TINY, 'Tiny Version'),
        (RESOURCE, 'Resource'),
        (NOW, 'Do it now'),
        (LATER, 'Do it later'),
        (CUSTOM, 'Custom'),
    )

    # URLMixin attributes
    urls_fields = ['pk', 'title_slug']
    urls_app_namespace = "goals"
    urls_model_name = "action"
    urls_icon_field = "icon"
    urls_image_field = "image"
    default_icon = "img/compass-grey.png"

    # String formatting patters for notifications
    _notification_title = "To {}:"  # Fill with the primary goal.
    _notification_text = "Time for me to {}"  # Fill with the notification_text

    # Data Fields
    title = models.CharField(
        max_length=256,
        db_index=True,
        help_text="A short (50 character) title for this Action"
    )
    title_slug = models.SlugField(max_length=256, db_index=True)

    behavior = models.ForeignKey(Behavior, verbose_name="behavior")
    action_type = models.CharField(
        max_length=32,
        default=CUSTOM,
        choices=ACTION_TYPE_CHOICES,
        db_index=True,
    )
    sequence_order = models.IntegerField(
        default=0,
        db_index=True,
        help_text="Order/number of action in stepwise sequence of behaviors"
    )
    default_trigger = models.OneToOneField(
        Trigger,
        blank=True,
        null=True,
        help_text="A trigger/reminder for this behavior",
        related_name="action_default"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="actions_updated",
        null=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="actions_created",
        null=True
    )

    @classmethod
    def get_create_starter_action_url(cls):
        return "{0}?actiontype={1}".format(
            reverse("goals:action-create"), cls.STARTER)

    @classmethod
    def get_create_tiny_action_url(cls):
        return "{0}?actiontype={1}".format(
            reverse("goals:action-create"), cls.TINY)

    @classmethod
    def get_create_resource_action_url(cls):
        return "{0}?actiontype={1}".format(
            reverse("goals:action-create"), cls.RESOURCE)

    @classmethod
    def get_create_now_action_url(cls):
        return "{0}?actiontype={1}".format(
            reverse("goals:action-create"), cls.NOW)

    @classmethod
    def get_create_later_action_url(cls):
        return "{0}?actiontype={1}".format(
            reverse("goals:action-create"), cls.LATER)

    @classmethod
    def get_create_custom_action_url(cls):
        return "{0}?actiontype={1}".format(
            reverse("goals:action-create"), cls.CUSTOM)

    class Meta(BaseBehavior.Meta):
        ordering = ['sequence_order', 'title']
        verbose_name = "Action"
        verbose_name_plural = "Actions"
        # add_action, change_action, delete_action are created by default.
        permissions = (
            ("view_action", "Can view Actions"),
            ("decline_action", "Can Decline Actions"),
            ("publish_action", "Can Publish Actions"),
        )

    def save(self, *args, **kwargs):
        """After saving an Action, we remove any stale GCM Notifications that
        were associated with the action, IF any of the fields used to generate
        a notification have changed.
        """
        super().save(*args, **kwargs)
        self.remove_queued_messages()

    def get_disable_trigger_url(self):
        args = [self.id, self.title_slug]
        return reverse("goals:action-disable-trigger", args=args)

    def disable_default_trigger(self):
        """Remove the default trigger from this action."""
        trigger_id = self.default_trigger.pk
        self.default_trigger = None
        self.save()

        # Delete the now-orphaned trigger
        Trigger.objects.filter(pk=trigger_id).delete()

    def get_async_icon_upload_url(self):
        return reverse("goals:file-upload", args=["action", self.id])

    def get_user_mapping(self, user):
        """Return the first UserAction object that matches this Action and the
        given user. There _should_ only be one of these. Returns None if the
        object is not found.

        Note: This method can be used by other apps that may have a generic
        relationships (e.g. notifications).

        """
        return self.useraction_set.filter(user=user, action=self).first()

    def remove_queued_messages(self):
        """Remove all GCMMessage objects that have a GenericForeignKey to this
        action instance.

        Once removed, the scheduled task will re-created any messages that need
        to be sent in the future.

        Historical note: I tried to check if fields had changed before doing
        this, but it was _hard_ with the related default_trigger field (because
        local values would be different types than what I read from the DB).
        I used something like: http://stackoverflow.com/a/15280630/182778 to
        build:

            _changed(['notification_text', 'default_trigger__time', ... ])

        """
        if not getattr(self, "_removed_queued_messages", False):
            # We need the content type for this object because we'll use it to
            # query the queued messages.
            action_type = ContentType.objects.get_for_model(self)

            params = {
                'content_type': action_type,
                'object_id': self.id,
                'success': None,  # only messages that haven't been sent.
            }
            GCMMessage.objects.filter(**params).delete()
            self._removed_queued_messages = True

    def get_notification_title(self, goal):
        # Let's try to un-capitalize the first character, but only if:
        # 1. it's not already lowercase, and
        # 2. the 2nd character isn't lowercase.
        title = goal.title
        if len(title) > 2 and not title[0:2].isupper():
            title = "{}{}".format(title[0].lower(), title[1:])
            return self._notification_title.format(title)
        return self._notification_title.format(title)

    def get_notification_text(self):
        text = self.notification_text
        if len(text) > 2 and not text[0:2].isupper():
            text = "{}{}".format(text[0].lower(), text[1:])
            return self._notification_text.format(text)
        return self._notification_text.format(text)

    objects = WorkflowManager()


# ----------------------------------
# Signals for public content models.
# ----------------------------------
@receiver(pre_save, sender=Action)
@receiver(pre_save, sender=Behavior)
@receiver(pre_save, sender=Goal)
@receiver(pre_save, sender=Category)
def clean_content(sender, instance, raw, using, **kwargs):
    # A mapping of model field names and the function that cleans them.
    clean_functions = {
        "title": clean_title,
        "subtitle": clean_title,
        "description": strip,
        "more_info": strip,
        "notification_text": clean_notification,
    }
    for field, func in clean_functions.items():
        if hasattr(instance, field):
            setattr(instance, field, func(getattr(instance, field)))


@receiver(post_delete, sender=Action)
@receiver(post_delete, sender=Behavior)
@receiver(post_delete, sender=Goal)
@receiver(post_delete, sender=Category)
def delete_model_icon(sender, instance, using, **kwargs):
    """Once a model instance has been deleted, this will remove its `icon` from
    the filesystem."""
    if hasattr(instance, 'icon') and instance.icon:
        instance.icon.delete()


@receiver(post_delete, sender=Action)
@receiver(post_delete, sender=Behavior)
def delete_model_image(sender, instance, using, **kwargs):
    """Once a model instance has been deleted, this will remove its `image`
    from the filesystem."""
    if hasattr(instance, 'image') and instance.image:
        instance.image.delete()


# -----------------------------------------------------------------------------
#
# Models that track a user's progress toward Goals, Behaviors, Actions.
#
# -----------------------------------------------------------------------------
class UserGoal(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    goal = models.ForeignKey(Goal)
    completed = models.BooleanField(default=False)
    completed_on = models.DateTimeField(blank=True, null=True)
    created_on = models.DateTimeField(auto_now_add=True)

    # Pre-rendered FK Fields.
    serialized_goal = JSONField(blank=True, default=dict, dump_kwargs=dump_kwargs)
    serialized_goal_progress = JSONField(blank=True, default=dict, dump_kwargs=dump_kwargs)
    serialized_user_categories = JSONField(blank=True, default=dict, dump_kwargs=dump_kwargs)
    serialized_user_behaviors = JSONField(blank=True, default=dict, dump_kwargs=dump_kwargs)
    serialized_primary_category = JSONField(blank=True, default=dict, dump_kwargs=dump_kwargs)

    class Meta:
        ordering = ['user', 'goal']
        unique_together = ("user", "goal")
        verbose_name = "User Goal"
        verbose_name_plural = "User Goals"

    def __str__(self):
        return "{0}".format(self.goal.title)

    def save(self, *args, **kwargs):
        self._serialize_goal()
        self._serialize_goal_progress()
        self._serialize_user_behaviors()
        self._serialize_user_categories()
        self._serialize_primary_category()
        return super().save(*args, **kwargs)

    def _serialize_goal(self):
        if self.goal:
            from .serializers import SimpleGoalSerializer
            self.serialized_goal = SimpleGoalSerializer(self.goal, user=self.user).data

    def _serialize_goal_progress(self):
        gp = self.goal_progress
        if gp:
            from .serializers import GoalProgressSerializer
            self.serialized_goal_progress = GoalProgressSerializer(gp).data

    def _serialize_user_categories(self):
        cats = self.get_user_categories()
        if cats:
            from .serializers import SimpleCategorySerializer
            self.serialized_user_categories = SimpleCategorySerializer(cats, many=True).data

    def _serialize_user_behaviors(self):
        behaviors = self.get_user_behaviors()
        if behaviors:
            from .serializers import SimpleBehaviorSerializer
            self.serialized_user_behaviors = SimpleBehaviorSerializer(behaviors, many=True).data

    def _serialize_primary_category(self):
        cat = self.get_primary_category()
        if cat:
            from .serializers import SimpleCategorySerializer
            self.serialized_primary_category = SimpleCategorySerializer(cat).data

    @property
    def goal_progress(self):
        """Returns the most recent GoalProgress instance related to this Goal."""
        try:
            params = {'user': self.user, 'goal': self.goal}
            return GoalProgress.objects.filter(**params).latest()
        except GoalProgress.DoesNotExist:
            return None

    @property
    def custom_triggers_allowed(self):
        """Check to see if the user/goal is in a Package where custom triggers
        are restricted. """
        return _custom_triggers_allowed(self.user, self)

    def get_user_behaviors(self):
        """Returns a QuerySet of published Behaviors related to this Goal, but
        restricts those behaviors to those which the user has selected.

        """
        bids = self.user.userbehavior_set.values_list('behavior_id', flat=True)
        return self.goal.behavior_set.filter(id__in=bids, state='published')

    def get_user_categories(self):
        """Returns a QuerySet of published Categories related to this Goal, but
        restricts those categories to those which the user has selected.

        NOTE: This method also looks up the user's `CategoryProgress` for
        each category, and appends a `progress_value` attribute.
        """
        # XXX: Not actually using this (category progress) at the moment.
        cids = self.user.usercategory_set.values_list('category__id', flat=True)
        results = self.goal.categories.filter(id__in=cids, state='published')
        for category in results:
            category.progress_value = 0
        return results

        # Tombstone for Dead Code
        tombstone = ("This Code should be dead, since we're not using "
                     "Category Progress values anymore")
        assert False, tombstone

        # Find all the lastest CategoryProgress objects for each user/category
        scores = {}
        for cid in cids:
            try:
                scores[cid] = CategoryProgress.objects.filter(
                    user=self.user,
                    category__id=cid
                ).latest().current_score
            except CategoryProgress.DoesNotExist:
                scores[cid] = 0.0

        results = self.goal.categories.filter(id__in=cids, state='published')
        for category in results:
            category.progress_value = scores.get(category.id, 0.0)
        return results

    def get_primary_category(self):
        """Return the first user-selected category that is a
        parent of this goal."""
        cat = self.get_user_categories().first()
        if cat is None:
            cat = self.goal.categories.first()
        return cat

    @property
    def progress_value(self):
        try:
            qs = self.goal.goalprogress_set.filter(user=self.user)
            return qs.latest().current_score
        except GoalProgress.DoesNotExist:
            return 0.0

    objects = UserGoalManager()


@receiver(pre_delete, sender=UserGoal, dispatch_uid="del_goal_behaviors")
def delete_goal_child_behaviors(sender, instance, using, **kwargs):
    """If a user is removing a goal, delete all of the user's selected
    behaviors that have *no other* parent goal."""
    # Get a list of all goals selected by the user, excluding the one
    # we're about to remove.
    user_goals = UserGoal.objects.filter(user=instance.user)
    user_goals = user_goals.exclude(id=instance.id)
    user_goals = user_goals.values_list('goal', flat=True)

    # Delete all the user's behaviors that lie ONLY in the goal we're
    # about to remove
    user_behaviors = instance.user.userbehavior_set.all()
    user_behaviors = user_behaviors.exclude(behavior__goals__in=user_goals)
    user_behaviors.delete()


class UserBehavior(models.Model):
    """A Mapping between Users and the Behaviors they've selected.

    NOTE: notifications for this are scheduled by the `create_notifications`
    management command.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    behavior = models.ForeignKey(Behavior)
    custom_trigger = models.ForeignKey(
        Trigger,
        blank=True,
        null=True,
        help_text="A User-defined trigger for this behavior"
    )
    completed = models.BooleanField(default=False)
    completed_on = models.DateTimeField(blank=True, null=True)
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "{0}".format(self.behavior.title)

    class Meta:
        ordering = ['user', 'behavior']
        unique_together = ("user", "behavior")
        verbose_name = "User Behavior"
        verbose_name_plural = "User Behaviors"

    @property
    def behavior_progress(self):
        """Returns the most recent GoalProgress instance related to this Goal."""
        try:
            return self.behaviorprogress_set.latest()
        except BehaviorProgress.DoesNotExist:
            return None

    @property
    def custom_triggers_allowed(self):
        """Check to see if the user/behavior is the child of a goal within a
        Package where custom triggers are restricted. """
        return _custom_triggers_allowed(self.user, self)

    def get_user_categories(self):
        """Returns a QuerySet of published Categories related to this Behavior,
        but restricts the result to those Categories which the user has selected.

        """
        # User-selected categories
        a = set(self.user.usercategory_set.values_list('category__id', flat=True))
        # Parent categories (through goals)
        b = set(self.behavior.goals.values_list("categories", flat=True))
        # The overlap
        ids = a.intersection(b)
        return Category.objects.published().filter(id__in=ids)

    def get_user_goals(self):
        """Returns a QuerySet of published Goals related to this Behavior, but
        restricts those goals to those which the user has selected."""
        gids = self.user.usergoal_set.values_list('goal__id', flat=True)
        return self.behavior.goals.filter(id__in=gids, state='published')

    def get_custom_trigger_name(self):
        """This should generate a unique name for this object's custom
        trigger."""
        return "custom trigger for userbehavior-{0}".format(self.id)

    def get_useractions(self):
        """Returns a QuerySet of UserAction objects whose Action is a child of
        this object's associated Behavior.
        """
        return self.user.useraction_set.filter(action__behavior=self.behavior)

    def get_actions(self):
        """Returns a QuerySet of published Actions related to this Behavior, but
        restricts the results to those which the user has selected.

        """
        uids = self.user.useraction_set.values_list('action_id', flat=True)
        return self.behavior.action_set.filter(id__in=uids, state='published')

    objects = UserBehaviorManager()


@receiver(pre_delete, sender=UserBehavior, dispatch_uid="del_behavior_actions")
def delete_behavior_child_actions(sender, instance, using, **kwargs):
    """If a user is removing a behavior, delete all of the user's selected
    actions that are a child of this behavior."""

    user_actions = instance.user.useraction_set.filter(
        action__behavior=instance.behavior
    )
    user_actions.delete()


@receiver(post_delete, sender=UserBehavior)
def remove_behavior_reminders(sender, instance, using, **kwargs):
    """If a user deletes ALL of their UserBehavior instances, we should also
    remove the currently-queued GCMMessage for the Behavior reminder.

    """
    # NOTE: All behavior reminders use the default trigger, and we're not
    # actually connecting them to any content types, so that's null.
    if not UserBehavior.objects.filter(user=instance.user).exists():
        try:
            from notifications.models import GCMMessage
            messages = GCMMessage.objects.for_model("behavior", include_null=True)
            messages = messages.filter(user=instance.user)
            messages.delete()
        except (ImportError, ContentType.DoesNotExist):
            pass


class UserAction(models.Model):
    """A Mapping between Users and the Actions they've selected.

    NOTE: notifications for this are scheduled by the `create_notifications`
    management command.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    action = models.ForeignKey(Action)
    custom_trigger = models.ForeignKey(
        Trigger,
        blank=True,
        null=True,
        help_text="A User-defined trigger for this behavior"
    )
    next_trigger_date = models.DateTimeField(
        blank=True,
        null=True,
        editable=False,
        help_text="The next date/time that a notification for this action "
                  "will be triggered (this is auto-populated and is in UTC)."
    )
    # In order to calculate "today's stats" for completed vs incomplete
    # actions, we need to be able to query backwards at least a day to find
    # actions that were scheduled in the past 24 hours.
    prev_trigger_date = models.DateTimeField(
        blank=True,
        null=True,
        editable=False,
        help_text="The previous date/time that a notification for this action "
                  "was be triggered (this is auto-populated and is in UTC)."
    )
    primary_goal = models.ForeignKey(
        Goal,
        blank=True,
        null=True,
        help_text="A primary goal associated with this action. Typically this "
                  "is the goal through which a user navigated to find the action."
    )

    # Pre-rendered FK Fields.
    serialized_action = JSONField(blank=True, default=dict, dump_kwargs=dump_kwargs)
    serialized_behavior = JSONField(blank=True, default=dict, dump_kwargs=dump_kwargs)
    # TODO: deprecate this field in favor of only using `serialized_trigger`
    serialized_custom_trigger = JSONField(blank=True, default=dict, dump_kwargs=dump_kwargs)
    serialized_primary_goal = JSONField(blank=True, default=dict, dump_kwargs=dump_kwargs)
    serialized_primary_category = JSONField(blank=True, default=dict, dump_kwargs=dump_kwargs)
    # This serialized trigger is a read-only field for either the default or
    # custom trigger.
    serialized_trigger = JSONField(blank=True, default=dict, dump_kwargs=dump_kwargs)
    created_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['user', 'action']
        unique_together = ("user", "action")
        verbose_name = "User Action"
        verbose_name_plural = "User Actions"

    def _serialize_action(self):
        if self.action:
            from .serializers import ActionSerializer
            self.serialized_action = ActionSerializer(self.action).data

    def _serialize_behavior(self):
        if self.user_behavior and self.user_behavior.behavior:
            from .serializers import BehaviorSerializer
            behavior = self.user_behavior.behavior
            self.serialized_behavior = BehaviorSerializer(behavior).data

    def _serialize_custom_trigger(self):
        if self.custom_trigger:
            from .serializers import CustomTriggerSerializer
            self.serialized_custom_trigger = CustomTriggerSerializer(self.custom_trigger).data
        else:
            self.serialized_custom_trigger = None

    def _serialize_primary_goal(self):
        from .serializers import SimpleGoalSerializer
        pg = self.get_primary_goal()
        if pg:
            self.serialized_primary_goal = SimpleGoalSerializer(pg, user=self.user).data

    def _serialize_primary_category(self):
        cat = self.get_primary_category()
        if cat:
            from .serializers import SimpleCategorySerializer
            self.serialized_primary_category = SimpleCategorySerializer(cat).data

    def _serialize_trigger(self):
        # XXX call this *after* _serialize_custom_trigger
        # This a read-only field for triggers. If the user has a custom trigger,
        # that value gets added hear, otherwise this contains the serialized
        # default trigger.
        if self.serialized_custom_trigger:
            self.serialized_trigger = self.serialized_custom_trigger  # Yeah, just a copy :(
        elif self.default_trigger:
            from .serializers import CustomTriggerSerializer
            self.serialized_trigger = CustomTriggerSerializer(self.default_trigger).data

    def __str__(self):
        return "{0}".format(self.action.title)

    def _completed(self, state):
        """Return the UserCompletedAction objects for this UserAction."""
        return self.usercompletedaction_set.filter(state=state)

    @property
    def num_completed(self):
        return self._completed(UserCompletedAction.COMPLETED).count()

    @property
    def num_uncompleted(self):
        return self._completed(UserCompletedAction.UNCOMPLETED).count()

    @property
    def num_snoozed(self):
        return self._completed(UserCompletedAction.SNOOZED).count()

    @property
    def num_dismissed(self):
        return self._completed(UserCompletedAction.DISMISSED).count()

    @property
    def trigger(self):
        if self.custom_trigger_id or self.custom_trigger:
            return self.custom_trigger
        return self.default_trigger

    @property
    def next_reminder(self):
        """Returns next_trigger_date in the user's local timezone."""
        if self.next_trigger_date is not None:
            return to_localtime(self.next_trigger_date, self.user)
        return self.next()

    def next(self):
        """Return the next trigger datetime object in the user's local timezone
        or None. This method will either return the value of `next_trigger_date`
        or the next date/time generated from the trigger, whichever is *next*."""

        trigger_times = []
        if self.next_trigger_date and self.next_trigger_date > timezone.now():
            # Convert to the user's timezone.
            trigger_times.append(to_localtime(self.next_trigger_date, self.user))

        if self.trigger:
            trigger_times.append(self.trigger.next(user=self.user))

        trigger_times = list(filter(None, trigger_times))
        if len(trigger_times) > 0:
            return min(trigger_times)

        return None

    def _set_next_trigger_date(self):
        """Attempt to  stash this action's next trigger date so we can query
        for it. This first tries any custom triggers then uses the default
        trigger. The result may be None (it's possible some action's no longer
        have a future trigger).

        NOTE: Always store this in UTC.

        """
        # ---------------------------------------------------------------------
        # NOTE: Some triggers have time, but no date or recurrence. These will
        # automatically generate a `next` value IFF the current time is before
        # the trigger's time; However, when these get queued up, it seems the
        # prev_trigger_date eventually gets overwritten. We need to figure out
        # how to write that value when it makes sense, given that triggers are
        # queued up every few minutes.
        # ---------------------------------------------------------------------
        trigger = self.trigger
        if trigger:
            # This trigger retuns the date in the user's timezone, so convert
            # it back to UTC.
            next_date = trigger.next(user=self.user)
            next_date = to_utc(next_date)

            # Save the previous trigger date, but don't overwrite on subsequent
            # saves; Only save when `next_trigger_date` changes (and is not None)
            next_changed = (
                next_date != self.next_trigger_date and
                next_date != self.prev_trigger_date
            )
            if next_changed and self.next_trigger_date:
                self.prev_trigger_date = self.next_trigger_date

            self.next_trigger_date = next_date

            # If we get to this point and the previous trigger is none,
            # try to back-fill (generate it) using the recurrence (but not for
            # relative reminders)
            if self.prev_trigger_date is None and not self.is_relative:
                prev = self.trigger.previous(user=self.user)
                self.prev_trigger_date = to_utc(prev)

            # If the prev trigger is *still* None, it's possible this is a
            # non-recurring event or that we've run out of recurrences. If
            # that's the case, and next is in the past, prev == next.
            in_past = (
                self.next_trigger_date and
                self.next_trigger_date < timezone.now()
            )
            if self.prev_trigger_date is None and in_past:
                self.prev_trigger_date = self.next_trigger_date

    def save(self, *args, **kwargs):
        """Adds a hook to update the prev_trigger_date & next_trigger_date
        whenever this object is saved. You can control this with the following
        additional keyword argument:

        * update_triggers: (default is True).

        """
        self._serialize_action()
        self._serialize_behavior()
        self._serialize_primary_goal()
        self._serialize_primary_category()
        self._serialize_custom_trigger()
        self._serialize_trigger()  # Keep *after* custom_trigger
        if kwargs.pop("update_triggers", True):
            self._set_next_trigger_date()
        return super().save(*args, **kwargs)

    @property
    def user_behavior(self):
        """Return the `UserBehavior` object that is related to the Action's
        parent Behavior.

        Returns a UserBehavior instance or None.

        """
        qs = UserBehavior.objects.select_related('behavior')
        qs = qs.prefetch_related('behavior__goals')
        return qs.filter(user=self.user, behavior=self.action.behavior).first()

    def get_notification_title(self):
        """Return the string to be used in this user's notification title."""
        goal = self.get_primary_goal() or Goal(title='')
        return self.action.get_notification_title(goal)

    def get_notification_text(self):
        """Return the string to be used in this user's notification text."""
        return self.action.get_notification_text()

    def get_user_goals(self):
        """Returns a QuerySet of published Goals related to this Action (and
        it's parent Behavior), but restricts those goals to those which the
        user has selected."""
        user_behavior = self.user_behavior
        if user_behavior:
            return user_behavior.get_user_goals()
        return Goal.objects.none()

    def get_primary_goal(self):
        """Return a Goal (or None) representing the primary goal associated
        with this user's selected Action."""
        if self.primary_goal:
            result = self.primary_goal
        else:
            result = self.get_user_goals().first()
        if not result and self.user_behavior:
            # Somehow, this user has no goals selected for this Action/Behavior,
            # so fall back to the first goal on the parent behavior.
            result = self.user_behavior.behavior.goals.first()
        return result

    def get_primary_category(self):
        """Return a Category (or None) representing the primary category
        associated with this user's selected Action."""
        category = None
        goal = self.get_primary_goal()
        if goal:
            uc = UserCategory.objects.filter(
                category__in=goal.categories.all(),
                user=self.user
            ).first()
            if uc:
                category = uc.category
        if category is None:
            goal = self.action.behavior.goals.first()
            if goal:
                cat = goal.categories.first()
        return category

    @property
    def completed_today(self):
        """Return True if this action was completed today, False otherwise"""
        return self.user.usercompletedaction_set.filter(
            action=self.action,
            updated_on__range=local_day_range(self.user),
            state='completed'
        ).exists()

    @property
    def custom_triggers_allowed(self):
        """Check to see if the user/behavior is the child of a goal within a
        Package where custom triggers are restricted. """
        return _custom_triggers_allowed(self.user, self)

    @property
    def default_trigger(self):
        if not hasattr(self, "_default_trigger"):
            self._default_trigger = self.action.default_trigger
        return self._default_trigger

    def get_custom_trigger_name(self):
        """This should generate a unique name for this object's custom
        trigger."""
        return "custom trigger for useraction-{0}".format(self.id)

    def queued_notifications(self):
        msgs = self.user.gcmmessage_set.filter(object_id=self.action.id)
        msgs = msgs.order_by('-deliver_on').distinct()
        return msgs

    objects = UserActionManager()


@receiver(post_save, sender=UserAction, dispatch_uid="create-parent-userbehavior")
def create_parent_user_behavior(sender, instance, using, **kwargs):
    """If a user doens't have a UserBehavior object for the UserAction's
    parent behavior this will create one.

    """
    params = {'user': instance.user, 'behavior': instance.action.behavior}
    if not UserBehavior.objects.filter(**params).exists():
        UserBehavior.objects.create(
            user=instance.user,
            behavior=instance.action.behavior
        )


@receiver(post_save, sender=UserAction, dispatch_uid="create-relative-reminder")
def create_relative_reminder(sender, instance, created, raw, using, **kwargs):
    """When a UserAction is created, we need to look at it's default_trigger
    and see if it's a relative reminder. If so, we automatically create a
    custom trigger for the user filling in it's trigger_date based on the
    UserAction's creation date.

    """
    is_relative = (
        instance.custom_trigger is None and
        instance.default_trigger is not None and
        instance.default_trigger.is_relative
    )
    if created and is_relative:
        trigger = Trigger.objects.create(
            user=instance.user,
            name="Trigger for {}".format(instance),
            time=instance.default_trigger.time,
            trigger_date=instance.default_trigger.trigger_date,
            recurrences=instance.default_trigger.recurrences,
            start_when_selected=instance.default_trigger.start_when_selected,
            stop_on_complete=instance.default_trigger.stop_on_complete,
            relative_value=instance.default_trigger.relative_value,
            relative_units=instance.default_trigger.relative_units
        )
        trigger.trigger_date = trigger.relative_trigger_date(instance.created_on)
        trigger.save()
        instance.custom_trigger = trigger
        instance.save()


@receiver(notification_snoozed)
def reset_next_trigger_date_when_snoozed(sender, message, user,
                                         related_object, deliver_on, **kwargs):
    """If a user snoozes a notification (in the notifications app), this function
    will try to update the relevant UserAction's `next_trigger_date`.

    """
    if related_object and message.content_type.name.lower() == 'action':
        ua = related_object.useraction_set.filter(user=user).first()
        if ua and deliver_on:
            ua.next_trigger_date = deliver_on
            ua.save(update_triggers=False)


@receiver(post_delete, sender=UserAction)
def remove_action_reminders(sender, instance, using, **kwargs):
    """If a user deletes one of their UserAction instances, we should also
    remove the GCMMessage associated with it, so they don't get a
    notification.

    NOTE: GCMMessages have a generic relationship to the Action
    """
    # Remove any custom triggers associated with this object.
    try:
        if instance.custom_trigger:
            instance.custom_trigger.delete()
    except Trigger.DoesNotExist:
        # This really shouldn't happen, but sometimes it does when cleaning
        # up generated objects in our test suite
        pass

    try:
        # Remove any pending notifications
        from notifications.models import GCMMessage
        action_type = ContentType.objects.get_for_model(Action)
        messages = GCMMessage.objects.filter(
            content_type=action_type,
            object_id=instance.action.id,
            user=instance.user
        )
        messages.delete()
    except (ImportError, ContentType.DoesNotExist):
        pass


class UserCompletedAction(models.Model):
    """Users can tell us they "completed" an Action. This is represented in
    the mobile app by a 'I did it' button.

    Note that there may be many instances of this model for a user/action, and
    that an aggregate of these tells us how often a user performs (or says they
    perform) this action.

    """
    UNCOMPLETED = 'uncompleted'
    COMPLETED = 'completed'
    DISMISSED = 'dismissed'
    SNOOZED = 'snoozed'
    UNSET = '-'

    STATE_CHOICES = (
        (UNCOMPLETED, 'Uncompleted'),
        (COMPLETED, 'Completed'),
        (DISMISSED, 'Dismissed'),
        (SNOOZED, 'Snoozed'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    useraction = models.ForeignKey(UserAction)
    action = models.ForeignKey(Action)
    state = models.CharField(
        max_length=32,
        default=UNSET,
        choices=STATE_CHOICES
    )
    updated_on = models.DateTimeField(auto_now=True)
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "{0}".format(self.action.title)

    class Meta:
        ordering = ['-updated_on', 'user', 'action']
        verbose_name = "User Completed Action"
        verbose_name_plural = "User Completed Action"

    @property
    def uncompleted(self):
        return self.state == self.UNCOMPLETED

    @property
    def completed(self):
        return self.state == self.COMPLETED

    @property
    def dismissed(self):
        return self.state == "dismissed"

    @property
    def snoozed(self):
        return self.state == "snoozed"


@receiver(post_save, sender=UserCompletedAction, dispatch_uid="action-completed")
def action_completed(sender, instance, created, raw, using, **kwargs):
    """Record metrics when a UserCompletedAction status is updated."""
    if instance.state:
        key = "action-{}".format(instance.state)
        metric(key, category="User Interactions")


class UserCategory(models.Model):
    """A Mapping between users and specific categories."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    category = models.ForeignKey(Category)
    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "{0}".format(self.category.title)

    class Meta:
        ordering = ['user', 'category']
        unique_together = ("user", "category")
        verbose_name = "User Category"
        verbose_name_plural = "User Categories"

    @property
    def custom_triggers_allowed(self):
        """Check to see if the user/category is a Package where custom triggers
        are restricted."""
        return _custom_triggers_allowed(self.user, self)

    def get_user_goals(self):
        """Returns a QuerySet of published Goals related to this Category, but
        restricts those goals to those which the user has selected."""
        gids = self.user.usergoal_set.values_list('goal__id', flat=True)
        return self.category.goals.filter(id__in=gids, state='published')

    @property
    def progress_value(self):
        try:
            qs = self.category.categoryprogress_set.filter(user=self.user)
            return qs.latest().current_score
        except CategoryProgress.DoesNotExist:
            return 0.0

    objects = UserCategoryManager()


@receiver(pre_delete, sender=UserCategory, dispatch_uid="del_cat_goals")
def delete_category_child_goals(sender, instance, using, **kwargs):
    """If a user is removing a category, delete all of the user's selected
    goals that have *no other* parent category."""
    # Get a list of all categories selected by the user, excluding the one
    # we're about to remove.
    user_categories = UserCategory.objects.filter(user=instance.user)
    user_categories = user_categories.exclude(id=instance.id)
    user_categories = user_categories.values_list('category', flat=True)

    # Delete all the user's goals that lie ONLY in the category we're
    # about to remove
    user_goals = instance.user.usergoal_set.all()
    user_goals = user_goals.exclude(goal__categories__in=user_categories)
    user_goals.delete()


@receiver(post_save, sender=UserCategory, dispatch_uid="adopt_usercategories")
@receiver(post_save, sender=UserGoal, dispatch_uid="adopt_usergoals")
@receiver(post_save, sender=UserBehavior, dispatch_uid="adopt_userbehaviors")
@receiver(post_save, sender=UserAction, dispatch_uid="adopt_useractions")
def user_adopted_content(sender, instance, created, raw, using, **kwargs):
    """Record some metrics when a user adopts a piece of behavior content."""
    if created:
        key = "{}-created".format(sender.__name__.lower())
        metric(key, category="User Interactions")


@receiver(pre_save, sender=UserAction, dispatch_uid='bust_useraction_cache')
@receiver(pre_save, sender=UserBehavior, dispatch_uid='bust_userbehavior_cache')
@receiver(pre_save, sender=UserGoal, dispatch_uid='bust_usergoal_cache')
@receiver(pre_save, sender=UserCategory, dispatch_uid='bust_usercategory_cache')
def bust_cache(sender, instance, raw, using, **kwargs):
    """This is a little messy, but whenever a user's mapping to content is saved
    we need to bust some cache values. This is mostly for the giant api endpoint
    that exposes a lot of user data (e.g. in the userprofile app).

    # TODO: extend this to bust all cache keys related to User* objects?

    """
    # A mapping of model to cache keys
    cache_key = {
        UserAction: '{}-User.get_actions',
        UserBehavior: '{}-User.get_behaviors',
        UserGoal: '{}-User.get_goals',
        UserCategory: '{}-User.get_categories',
    }
    cache_key = cache_key.get(sender, None)
    if cache_key:
        cache_key = cache_key.format(instance.user.id)
        cache.delete(cache_key)


class BehaviorProgress(models.Model):
    """Encapsulates a user's progress & history toward certain behaviors.

    The following are aggregates for a user's progress on Actions within this
    Behavior. They're populated via the `aggregate_progress` management command.

    * daily_actions_total
    * daily_actions_completed
    * daily_action_progress

    NOTE: The OFF_COURSE, SEEKING, and ON_COURSE values have essentially been
    depricated, so this model really only aggregates up completed action
    values at the moment.

    TODO: Remove these ^ old fields.

    """
    OFF_COURSE = 1
    SEEKING = 2
    ON_COURSE = 3

    PROGRESS_CHOICES = (
        (OFF_COURSE, "Off Course"),
        (SEEKING, "Seeking"),
        (ON_COURSE, "On Course"),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    user_behavior = models.ForeignKey(UserBehavior)

    # Status is for user-input feedback (e.g. the daily check-in)
    status = models.IntegerField(choices=PROGRESS_CHOICES)

    # Action progress is calculated based on completed vs. non-completed Actions
    daily_actions_total = models.IntegerField(default=0)
    daily_actions_completed = models.IntegerField(default=0)
    daily_action_progress = models.FloatField(default=0)

    reported_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-reported_on']
        get_latest_by = "reported_on"
        verbose_name = "Behavior Progress"
        verbose_name_plural = "Behavior Progresses"

    def __str__(self):
        return self.get_status_display()

    def _calculate_action_progress(self):
        """Count the user's scheduled + completed actions that are children of
        the related UserBehavior.behavior, but only do this for the date this
        progress item was saved (so we can back-fill old action progress if
        available).

        This method will overwrite the following fields:

        - daily_actions_total
        - daily_actions_completed
        - daily_action_progress

        """
        date_range = local_day_range(self.user, self.reported_on)

        # NOTE: UserAction.next_trigger_date gets updated daily, so we can't
        # use it to query for historical data. Intead, we need to look at the
        # history of completed information (UserCompletedAction objects where
        # the action's parent behavior matches this behavior).
        ucas = self.user.usercompletedaction_set.filter(
            user=self.user,
            action__behavior=self.user_behavior.behavior,
            updated_on__range=date_range
        )
        self.daily_actions_total = ucas.count()
        self.daily_actions_completed = ucas.filter(
            state=UserCompletedAction.COMPLETED
        ).count()

        if self.daily_actions_total > 0:
            self.daily_action_progress = (
                self.daily_actions_completed / self.daily_actions_total
            )

    def save(self, *args, **kwargs):
        self._calculate_action_progress()
        super().save(*args, **kwargs)

    @property
    def daily_action_progress_percent(self):
        """The `daily_action_progress` value as integer percent."""
        return int(self.daily_action_progress * 100)

    @property
    def status_display(self):
        return self.get_status_display()

    @property
    def behavior(self):
        return self.user_behavior.behavior


@receiver(post_save, sender=BehaviorProgress, dispatch_uid="recalc_goal_progress")
def recalculate_goal_progress(sender, instance, created, **kwargs):
    """This signal handler will re-calculate the most recent GoalProgress
    instance when a BehaviorProgress is created."""
    if created:
        # Get all possible goal ids associated with the user
        for gid in instance.user_behavior.behavior.goals.values_list("id", flat=True):
            try:
                # Recalculate the score from all related BehaviorProgress objects
                gp = GoalProgress.objects.filter(user=instance.user, goal__id=gid).latest()
                gp.recalculate_score()
                gp.save()
            except GoalProgress.DoesNotExist:
                pass


class GoalProgressManager(models.Manager):
    """Custom manager for the `GoalProgress` class that includes a method
    to generate scores for a User's progress toward a Goal.

    NOTE: This is defined here (in models.py) instead of in managers.py, so
    we have access to the Goal & BehaviorProgress models.

    """

    def _get_or_update(self, user, goal, scores, current_time):
        # check to see if we've already got a GoalProgress object for this date
        start, end = dateutils.date_range(current_time)

        # do the aggregation
        score_total = sum(scores)
        score_max = len(scores) * BehaviorProgress.ON_COURSE

        try:
            gp = self.filter(
                user=user,
                goal=goal,
                reported_on__range=(start, end)
            ).latest()
            gp.current_total = score_total
            gp.max_total = score_max
            gp.save()
        except self.model.DoesNotExist:
            gp = self.create(
                user=user,
                goal=goal,
                current_total=score_total,
                max_total=score_max
            )
        return gp

    def generate_scores(self, user):
        created_objects = []
        current_time = timezone.now()

        # Get all the goals that a user has selected IFF that user has also
        # selected some Behaviors.
        #
        # This is the intersection of:
        # - the set of goal ids that contain behavior's i've selected
        # - the set of goals i've selected
        ubgs = UserBehavior.objects.filter(user=user)
        ubgs = set(ubgs.values_list('behavior__goals__id', flat=True))

        goal_ids = UserGoal.objects.filter(user=user)
        goal_ids = set(goal_ids.values_list('goal', flat=True))
        goal_ids = goal_ids.intersection(ubgs)

        for goal in Goal.objects.filter(id__in=goal_ids):
            # Get all the User's selected behavior (ids) within that goal.
            behaviors = UserBehavior.objects.filter(
                user=user,
                behavior__goals=goal
            ).values_list('behavior', flat=True)

            if behaviors.exists():
                # All the self-reported scores up to this date for this goal
                scores = BehaviorProgress.objects.filter(
                    user_behavior__behavior__id__in=behaviors,
                    user=user,
                    reported_on__lte=current_time
                ).values_list('status', flat=True)

                # Create a GoalProgress object for this data
                gp = self._get_or_update(user, goal, scores, current_time)
                created_objects.append(gp.id)
        return self.get_queryset().filter(id__in=created_objects)


class GoalProgress(models.Model):
    """Aggregates data from `BehaviorProgress` up to 'today'.

    The following fields are used to aggregate a user's completed v. incomplete
    Actions withing this goal (and it's child behaviors):

    * daily_actions_total
    * daily_action_completed
    * daily_action_progress
    * weekly_actions_total
    * weekly_actions_completed
    * weekly_action_progress
    * actions_total
    * actions_completed
    * action_progress

    The following fields store the user's end-of-day "How are doing" data
    related to the selected goal. This daily check-in value gets averaged over
    the past 7 and 30 days (weekly, monthly)

    * daily_checkin
    * weekly_checkin
    * monthly_checkin

    The following fields were used to aggregate the now-deprecated
    BehaviorProgress data up to the goal.

    * current_score
    * current_total
    * max_total

    TODO: ^ remove these fields and associated code?

    ----

    NOTE: These values are populated via the `aggregate_progress` command.

    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    goal = models.ForeignKey(Goal)
    usergoal = models.ForeignKey(UserGoal, null=True)

    # Aggregating the self-reported Behavior Progress
    current_score = models.FloatField(default=0)
    current_total = models.FloatField(default=0)
    max_total = models.FloatField(default=0)

    # Daily check-in fields, for a user's "How are you doing on this Goal"
    # data. Weekly and Monthly values are averages over the past 7 and 30 days.
    daily_checkin = models.IntegerField(default=0)
    weekly_checkin = models.FloatField(default=0)
    monthly_checkin = models.FloatField(default=0)

    # Aggregating the user's completed Actions for the day
    daily_actions_total = models.IntegerField(default=0)
    daily_actions_completed = models.IntegerField(default=0)
    daily_action_progress = models.FloatField(default=0)

    # Weekly aggregation for the user's completed Actions
    weekly_actions_total = models.IntegerField(default=0)
    weekly_actions_completed = models.IntegerField(default=0)
    weekly_action_progress = models.FloatField(default=0)

    # Historical aggregations of the user's completed actions. See the
    # PROGRESS_HISTORY_DAYS settings.
    actions_total = models.IntegerField(default=0)
    actions_completed = models.IntegerField(default=0)
    action_progress = models.FloatField(default=0)

    reported_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'goal', 'reported_on')
        ordering = ['-reported_on']
        get_latest_by = "reported_on"
        verbose_name = "Goal Progress"
        verbose_name_plural = "Goal Progresses"

    def __str__(self):
        return "{}".format(self.current_score)

    @property
    def daily_action_progress_percent(self):
        """The `daily_action_progress` value as integer percent."""
        return int(self.daily_action_progress * 100)

    @property
    def weekly_action_progress_percent(self):
        """The `weekly_action_progress` value as integer percent."""
        return int(self.weekly_action_progress * 100)

    @property
    def action_progress_percent(self):
        """The `action_progress` value as integer percent."""
        return int(self.action_progress * 100)

    def child_behaviorprogresses(self):
        """Returns a queryset of BehaviorProgress instances whose related
        Behavior is a child of this object's Goal.

        """
        lookup = {'user_behavior__behavior__goals__in': [self.goal]}
        return self.user.behaviorprogress_set.filter(**lookup)

    def _calculate_actions_stats(self, days=1):
        """Calculate the actions stats from the BehaviorProgress model over
        some time period ending with either this model's reported_on date or
        today's date if if `reported_on` is None.

        Returns a 3-tuple of the following: (completed, total, progress), where

        * completed - the number of actions completed
        * total - the total number of actions scheduled
        * progress - the percentage (as a float): completed / total

        """
        start, end = local_day_range(self.user, self.reported_on)
        start = start - timedelta(days=days)

        # Run the aggregate over the relevant BehaviorProgress objects.
        qs = self.child_behaviorprogresses().filter(reported_on__range=(start, end))
        qs = qs.aggregate(Sum('daily_actions_total'), Sum('daily_actions_completed'))

        total = qs.get('daily_actions_total__sum', 0) or 0
        completed = qs.get('daily_actions_completed__sum', 0) or 0
        progress = 0
        if total > 0:
            progress = completed / total
        return (completed, total, progress)

    def calculate_daily_action_stats(self):
        """Aggregate the BehaviorProgress action status saved on the same day."""
        completed, total, progress = self._calculate_actions_stats(days=1)
        self.daily_actions_completed = completed
        self.daily_actions_total = total
        self.daily_action_progress = progress

    def calculate_weekly_action_stats(self):
        """Aggregate the BehaviorProgress action stats for the past week."""
        completed, total, progress = self._calculate_actions_stats(days=7)
        self.weekly_actions_completed = completed
        self.weekly_actions_total = total
        self.weekly_action_progress = progress

    def calculate_aggregate_action_stats(self):
        """Aggregate the BehaviorProgress action stats."""
        completed, total, progress = self._calculate_actions_stats(
            days=settings.PROGRESS_HISTORY_DAYS
        )
        self.actions_completed = completed
        self.actions_total = total
        self.action_progress = progress

    def _calculate_score(self, digits=2):
        v = 0
        if self.max_total > 0:
            v = round(self.current_total / self.max_total, digits)
        self.current_score = v

    def recalculate_score(self):
        """Recalculate all of the BehaviorProgress values for the current date,
        updating the relevant score-related fields."""
        start = self.reported_on.replace(hour=0, minute=0, second=0, microsecond=0)
        end = self.reported_on.replace(hour=23, minute=59, second=59, microsecond=999999)

        scores = self.child_behaviorprogresses()
        scores = scores.filter(reported_on__range=(start, end))
        scores = scores.values_list('status', flat=True)

        self.current_total = sum(scores)
        self.max_total = len(scores) * BehaviorProgress.ON_COURSE
        self._calculate_score()

    def _calculate_checkin_average(self, days):
        report_date = self.reported_on if self.reported_on else timezone.now()
        from_date = report_date - timedelta(days=days)
        to_date = self.reported_on
        result = GoalProgress.objects.filter(
            user=self.user,
            goal=self.goal,
            usergoal=self.usergoal,
            reported_on__range=(from_date, to_date)
        ).aggregate(Avg('daily_checkin'))
        return result.get('daily_checkin__avg', 0) or 0

    def _weekly_checkin_average(self):
        self.weekly_checkin = self._calculate_checkin_average(7)

    def _monthly_checkin_average(self):
        self.monthly_checkin = self._calculate_checkin_average(30)

    def save(self, *args, **kwargs):
        # Aggregate Behavior scores
        self._calculate_score()

        # Action-related stats
        self.calculate_daily_action_stats()
        self.calculate_weekly_action_stats()
        self.calculate_aggregate_action_stats()

        # Daily "how am i doing" stats and averages.
        self._weekly_checkin_average()
        self._monthly_checkin_average()
        return super().save(*args, **kwargs)

    @property
    def text_glyph(self):
        """show a unicode arrow representing the compass needle; used in admin"""
        if self.current_score < 0.25:
            return u"\u2193"  # down (south)
        elif self.current_score >= 0.25 and self.current_score < 0.4:
            return u"\u2198"  # down-right (southeast)
        elif self.current_score >= 0.4 and self.current_score < 0.7:
            return u"\u2192"  # right (east)
        elif self.current_score >= 0.7 and self.current_score < 0.9:
            return u"\u2197"  # right-up (northeast)
        elif self.current_score >= 0.9:
            return u"\u2191"  # up (north)

    objects = GoalProgressManager()


class CategoryProgressManager(models.Manager):
    """Custom manager for the `CategoryProgress` class that includes a method
    to generate scores for a User's progress."""

    def _get_or_update(self, user, category, current_score, current_time):
        # check to see if we've already got a CategoryProgress object for
        # the current date
        start, end = dateutils.date_range(current_time)
        current_score = round(current_score, 2)

        try:
            cp = self.filter(
                user=user,
                category=category,
                reported_on__range=(start, end)
            ).latest()
            cp.current_score = current_score
            cp.save()
        except self.model.DoesNotExist:
            # Create a CategoryProgress object for this data
            cp = self.create(
                user=user,
                category=category,
                current_score=round(current_score, 2),
            )
        return cp

    def generate_scores(self, user):
        created_objects = []
        current_time = timezone.now()

        # Get all the categories that a user has selected IFF there are also
        # some goalprogress objects for that category
        #
        # This is the intersection of:
        # - the set of categories that contain goals that i've selected
        # - the set of categories i've selected
        ug_cats = UserGoal.objects.filter(user=user)
        ug_cats = set(ug_cats.values_list('goal__categories__id', flat=True))
        cat_ids = UserCategory.objects.filter(user=user)
        cat_ids = set(cat_ids.values_list('category__id', flat=True))
        cat_ids = cat_ids.intersection(ug_cats)

        # NOTE: Average GoalProgress for the last 7 days
        start, end = dateutils.date_range(current_time)
        start = start - timedelta(days=7)

        for cat in Category.objects.filter(id__in=cat_ids):
            # Average all latest relevant GoalProgress scores
            results = GoalProgress.objects.filter(
                user=user,
                goal__categories=cat,
                reported_on__range=(start, end)
            ).aggregate(Avg("current_score"))

            # NOTE: Result of averaging the current scores could be None
            current_score = results.get('current_score__avg', 0) or 0

            # Create a CategoryProgress object for this data
            cp = self._get_or_update(user, cat, current_score, current_time)
            created_objects.append(cp.id)
        return self.get_queryset().filter(id__in=created_objects)


class CategoryProgress(models.Model):
    """Agregates score data from `GoalProgress` up to 'today'."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    category = models.ForeignKey(Category)
    current_score = models.FloatField(default=0)
    reported_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-reported_on']
        get_latest_by = "reported_on"
        verbose_name = "Category Progress"
        verbose_name_plural = "Category Progresses"

    def __str__(self):
        return "{}".format(self.current_score)

    def recalculate_score(self, digits=2):
        """Recalculate all of the Progress values for the current date,
        updating the relevant score-related fields.

        This method Averages the user's GoalProgress scores for all goals
        related to this category, for the most recent day.

        """
        goal_ids = self.category.goals.values_list("id", flat=True)
        start = self.reported_on.replace(hour=0, minute=0, second=0, microsecond=0)
        end = self.reported_on.replace(hour=23, minute=59, second=59, microsecond=999999)
        results = GoalProgress.objects.filter(
            user=self.user,
            goal__id__in=goal_ids,
            reported_on__range=(start, end)
        ).aggregate(Avg("current_score"))
        self.current_score = round(results.get('current_score__avg', 0), digits)

    @property
    def text_glyph(self):
        """show a unicode arrow representing the compass needle; used in admin"""
        if self.current_score < 0.25:
            return u"\u2193"  # down (south)
        elif self.current_score >= 0.25 and self.current_score < 0.4:
            return u"\u2198"  # down-right (southeast)
        elif self.current_score >= 0.4 and self.current_score < 0.7:
            return u"\u2192"  # right (east)
        elif self.current_score >= 0.7 and self.current_score < 0.9:
            return u"\u2197"  # right-up (northeast)
        elif self.current_score >= 0.9:
            return u"\u2191"  # up (north)

    objects = CategoryProgressManager()


class PackageEnrollment(models.Model):
    """A mapping of users who've been enrolled in various *Packaged Content*
    e.g. Categories. This model tracks when they were enrolled, which categories
    they were enrolled in, and who enrolled them.

    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    category = models.ForeignKey(Category)
    goals = models.ManyToManyField(Goal)
    prevent_custom_triggers = models.BooleanField(
        default=False,
        help_text="Setting this option will prevent users from overriding the "
                  "default reminder times for actions within the selected goals."
    )
    accepted = models.BooleanField(default=False)
    enrolled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='enrolled'
    )
    updated_on = models.DateTimeField(auto_now=True)
    enrolled_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['enrolled_on']
        verbose_name = "Package Enrollment"
        verbose_name_plural = "Package Enrollments"

    def __str__(self):
        return "{0} enrolled on {1}".format(
            self.user.get_full_name(),
            self.enrolled_on
        )

    @property
    def rendered_consent_summary(self):
        return self.category.rendered_consent_summary

    @property
    def rendered_consent_more(self):
        return self.category.rendered_consent_more

    def get_absolute_url(self):
        """Currently, this is the PackageDetailView, which provides a list of
        enrollments."""
        return reverse("goals:package-detail", args=[self.pk])

    def get_accept_url(self):
        return reverse("goals:accept-enrollment", args=[self.pk])

    def accept(self):
        self.accepted = True
        self.save()
        self.create_user_mappings()

    def create_user_mappings(self):
        """Creates all of the User-mappings for the associated categories and
        all child content."""
        # This is terribly inefficient, because we'll likely be doing
        # this for a number of users at once.
        UserCategory.objects.get_or_create(user=self.user, category=self.category)

        # Enroll the user in the behaviors.
        goals = self.goals.all()
        for goal in goals:
            UserGoal.objects.get_or_create(user=self.user, goal=goal)

        # Enroll the User in the Behaviors
        behaviors = Behavior.objects.published().filter(goals=goals).distinct()
        for behavior in behaviors:
            UserBehavior.objects.get_or_create(user=self.user, behavior=behavior)

        # Enroll the User in the Actions
        actions = Action.objects.published().filter(behavior__in=behaviors)
        actions = actions.distinct()
        for action in actions:
            UserAction.objects.get_or_create(user=self.user, action=action)

    objects = PackageEnrollmentManager()


@receiver(post_save, sender=PackageEnrollment, dispatch_uid="notifiy_for_new_package")
def notify_for_new_package(sender, instance, created, **kwargs):
    """Create and schedule a GCMMEssage for users that have a device registered,
    once they've been enrolled in a new package.

    """
    if created and instance.user.gcmdevice_set.exists():
        from notifications.models import GCMMessage
        GCMMessage.objects.create(
            user=instance.user,
            title="You've been enrolled.",
            message="Welcome to {0}".format(instance.category.title),
            deliver_on=timezone.now(),
            obj=instance,
        )


# Convenience functions
# ---------------------

def popular_actions(top=10):
    """Returns a list of [(title, count), ... ] tuples for popular Actions."""

    cursor = connection.cursor()
    query = """
select count(action_id) as aid_count, action_id
from goals_useraction group by action_id
order by aid_count desc
limit %s
"""
    cursor.execute(query, [top])
    results = cursor.fetchall()

    # split out the counts & action ids so we can look up the relevant titles
    counts = [t[0] for t in results]
    ids = [t[1] for t in results]
    titles = Action.objects.filter(id__in=ids).values_list('title', flat=True)
    return list(zip(titles, counts))


def popular_behaviors(top=10):
    """Returns a list of [(title, count), ... ] tuples for popular Behaviors."""

    cursor = connection.cursor()
    query = """
select count(behavior_id) as bid_count, behavior_id
from goals_userbehavior group by behavior_id
order by bid_count desc
limit %s
"""
    cursor.execute(query, [top])
    results = cursor.fetchall()

    # split out the counts & action ids so we can look up the relevant titles
    counts = [t[0] for t in results]
    ids = [t[1] for t in results]
    titles = Behavior.objects.filter(id__in=ids).values_list('title', flat=True)
    return list(zip(titles, counts))


def popular_goals(top=10):
    """Returns a list of [(title, count), ... ] tuples for popular Goals."""

    cursor = connection.cursor()
    query = """
select count(goal_id) as gid_count, goal_id
from goals_usergoal group by goal_id
order by gid_count desc
limit %s
"""
    cursor.execute(query, [top])
    results = cursor.fetchall()

    # split out the counts & action ids so we can look up the relevant titles
    counts = [t[0] for t in results]
    ids = [t[1] for t in results]
    titles = Goal.objects.filter(id__in=ids).values_list('title', flat=True)
    return list(zip(titles, counts))


def popular_categories(top=10):
    """Returns a list of [(title, count), ... ] tuples for popular Categories."""

    cursor = connection.cursor()
    query = """
select count(category_id) as cid_count, category_id
from goals_usercategory group by category_id
order by cid_count desc
limit %s
"""
    cursor.execute(query, [top])
    results = cursor.fetchall()

    # split out the counts & action ids so we can look up the relevant titles
    counts = [t[0] for t in results]
    ids = [t[1] for t in results]
    titles = Category.objects.filter(id__in=ids).values_list('title', flat=True)
    return list(zip(titles, counts))
