from django.contrib import admin
from django.contrib.messages import ERROR
from django.db import transaction

from django_fsm import TransitionNotAllowed

from utils.admin import UserRelatedModelAdmin

from . import models


class ContentWorkflowAdmin(admin.ModelAdmin):
    """This class adds action methods for changing the state of content."""

    actions = ['set_draft', 'set_review', 'set_declined', 'set_published']

    def _transition_to(self, request, queryset, method, message):
        try:
            with transaction.atomic():
                for obj in queryset:
                    getattr(obj, method)()  # Call the transition method.
                    obj.save(updated_by=request.user)
            self.message_user(request, message)
        except TransitionNotAllowed as err:
            self.message_user(request, err, level=ERROR)

    def set_draft(self, request, queryset):
        self._transition_to(request, queryset, "draft", "Items marked Draft")
    set_draft.short_description = "Mark as Draft"

    def set_review(self, request, queryset):
        self._transition_to(request, queryset, "review", "Items submitted for review")
    set_review.short_description = "Submit for Review"

    def set_declined(self, request, queryset):
        self._transition_to(request, queryset, "decline", "Items Declined")
    set_declined.short_description = "Decline Items"

    def set_published(self, request, queryset):
        self._transition_to(request, queryset, "publish", "Items Published")
    set_published.short_description = "Publish"


class CategoryAdmin(ContentWorkflowAdmin):
    list_display = (
        'title', 'title_slug', 'state', 'order', 'get_absolute_icon',
        'created_by', 'created_on', 'updated_by', 'updated_on',
    )
    search_fields = ['title', 'description', 'notes']
    list_filter = ('state', )
    prepopulated_fields = {"title_slug": ("title", )}

admin.site.register(models.Category, CategoryAdmin)


class GoalAdmin(ContentWorkflowAdmin):
    list_display = (
        'title', 'title_slug', 'state', 'in_categories', 'get_absolute_icon',
        'created_by', 'created_on', 'updated_by', 'updated_on',
    )
    search_fields = ['title', 'subtitle', 'description', 'outcome']
    list_filter = ('state', )
    prepopulated_fields = {"title_slug": ("title", )}

    def in_categories(self, obj):
        return ", ".join(sorted([cat.title for cat in obj.categories.all()]))

admin.site.register(models.Goal, GoalAdmin)


class TriggerAdmin(UserRelatedModelAdmin):
    list_display = ('name', 'trigger_type', 'time', 'location', 'user')
    prepopulated_fields = {"name_slug": ("name", )}
    search_fields = [
        'user__username', 'user__email', 'user__first_name', 'user__last_name',
        'name', 'location',
    ]
admin.site.register(models.Trigger, TriggerAdmin)


class BehaviorAdmin(ContentWorkflowAdmin):
    list_display = (
        'title', 'state', 'in_categories', 'in_goals',
        'get_absolute_icon', 'get_absolute_image',
        'created_by', 'created_on', 'updated_by', 'updated_on',
    )
    search_fields = [
        'title', 'source_notes', 'notes', 'more_info', 'description',
        'case', 'outcome', 'notification_text',
    ]
    list_filter = ('state', )
    prepopulated_fields = {"title_slug": ("title", )}

    def in_categories(self, obj):
        return ", ".join(sorted([cat.title for cat in obj.categories.all()]))

    def in_goals(self, obj):
        return ", ".join(sorted([g.title for g in obj.goals.all()]))
admin.site.register(models.Behavior, BehaviorAdmin)


class ActionAdmin(ContentWorkflowAdmin):
    list_display = (
        'title', 'state', 'behavior', 'sequence_order',
        'get_absolute_icon', 'get_absolute_image',
        'created_by', 'created_on', 'updated_by', 'updated_on',
    )
    search_fields = [
        'title', 'source_notes', 'notes', 'more_info', 'description',
        'case', 'outcome', 'notification_text',
    ]
    list_filter = ('state', )
    prepopulated_fields = {"title_slug": ("title", )}
admin.site.register(models.Action, ActionAdmin)


class UserCategoryAdmin(UserRelatedModelAdmin):
    list_display = (
        'user', 'user_email', 'user_first', 'user_last', 'category', 'created_on'
    )
    search_fields = (
        'user__username', 'user__email', 'user__first_name', 'user__last_name',
        'category__title', 'category__id'
    )

admin.site.register(models.UserCategory, UserCategoryAdmin)


class UserGoalAdmin(UserRelatedModelAdmin):
    list_display = (
        'user', 'user_email', 'user_first', 'user_last', 'goal', 'created_on'
    )
    search_fields = (
        'user__username', 'user__email', 'user__first_name', 'user__last_name',
        'goal__title', 'goal__id',
    )
admin.site.register(models.UserGoal, UserGoalAdmin)


class UserBehaviorAdmin(UserRelatedModelAdmin):
    list_display = (
        'user', 'user_email', 'user_first', 'user_last', 'behavior', 'created_on'
    )
    search_fields = (
        'user__username', 'user__email', 'user__first_name', 'user__last_name',
        'behavior__id', 'behavior__title',
    )
admin.site.register(models.UserBehavior, UserBehaviorAdmin)


class UserActionAdmin(UserRelatedModelAdmin):
    list_display = (
        'user', 'user_email', 'user_first', 'user_last', 'action', 'created_on'
    )
    search_fields = (
        'user__username', 'user__email', 'user__first_name', 'user__last_name',
        'action__id', 'action__title',
    )
admin.site.register(models.UserAction, UserActionAdmin)


class BehaviorProgressAdmin(UserRelatedModelAdmin):
    list_display = (
        'user', 'behavior', 'status', 'reported_on'
    )
admin.site.register(models.BehaviorProgress, BehaviorProgressAdmin)


class GoalProgressAdmin(UserRelatedModelAdmin):
    list_display = (
        'user', 'goal', 'current_total', 'max_total',
        'current_score', 'text_glyph', 'reported_on'
    )
admin.site.register(models.GoalProgress, GoalProgressAdmin)


class CategoryProgressAdmin(UserRelatedModelAdmin):
    list_display = (
        'user', 'category', 'current_score', 'text_glyph', 'reported_on'
    )
admin.site.register(models.CategoryProgress, CategoryProgressAdmin)
