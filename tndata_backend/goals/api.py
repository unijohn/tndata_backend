from rest_framework import permissions, viewsets

from . import models
from . import serializers


class IsOwner(permissions.BasePermission):
    """Only allow owners of an object to view/edit it."""

    def has_object_permission(self, request, view, obj):
        return obj.user == request.user


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Categories are containers for similar Goals. A Goal may appear in more
    than one category.

    Each Category has at least the following bits of information:

    * id: The unique database identifier for the category
    * order: Controls the order in which Categories are displayed.
    * title: The unique Title (or name) of the Category
    * title_slug: A url-friendly version of the title.
    * description: A short description of this Category. May contain markdown.
    * icon_url: A URL for an image associated with the category
    * goals: A list of goals that appear in this category. See the [Goals](/api/goals/)
        endpoint for more information.

    ## Category Endpoints

    Each category is available at an endpoint based on it's database ID: `/api/categories/{id}/`.

    ----

    """
    queryset = models.Category.objects.all()
    serializer_class = serializers.CategorySerializer


class GoalViewSet(viewsets.ReadOnlyModelViewSet):
    """Goals contain the following information:

    * id: The unique database identifier for the category
    * title: A unique Title (or name) for the goal.
    * title_slug: A url-friendly version of the title.
    * subtitle: A short, one-liner description for the goal (256 chars or less)
    * description: A longer description for the goal. May contain markdown.
    * outcome: Additional (optional) text that may describe an expected outcome
      of pursing this Goal.
    * icon_url: A URL for an image associated with the category
    * categories: A list of [Categories](/api/categories/) in which the goal appears.

    ## Goal Endpoints

    Each goal is available at an endpoint based on it's database ID: `/api/goals/{id}/`.

    ## Filtering

    Goals can be filtered using a querystring paramter. Currently, filtering is
    only availble for categories; i.e. You can retrieve goals for a category
    by providing a category id: `/api/goals/?category={category_id}`

    ----

    """
    queryset = models.Goal.objects.all()
    serializer_class = serializers.GoalSerializer

    def get_queryset(self):
        if 'category' in self.request.GET:
            self.queryset = self.queryset.filter(
                categories__id=self.request.GET['category']
            )
        return self.queryset


class TriggerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.Trigger.objects.all()
    serializer_class = serializers.TriggerSerializer


class BehaviorSequenceViewSet(viewsets.ReadOnlyModelViewSet):
    """A Behavior Sequence (aka a *Behavior* or *Sequence* is a abstract
    behavior as well as a potential container for concrete actions.

    Each BehaviorSequence object contains the following:

    * id: The unique database identifier for the category
    * name: A unique, but informal, internally-used name for the behavior.
    * name_slug: A url-friendly version of name.
    * title: A unique, Formal title. Use this to refer to this item.
    * description: A longer description for the goal. May contain markdown.
    * case: (optional) Brief description of why this is useful.
    * outcome: Additional (optional) text that may describe an expected outcome
      of pursing this Goal.
    * narrative_block: Persuasive narrative description, case, outcome of the behavior
    * external_resource = A link or reference to an outside resource necessary for adoption
    * default_trigger: A trigger/reminder for this behavior. See the
        (Trigger)[/api/triggers/] endpoint.
    * notification_text: Text of the message delivered through notifications
    * icon_url: A URL for an icon associated with the category
    * image_url: (optional) Possibly larger image for this item.
    * goals: A list of goals in which this BehaviorSequence appears.

    ## Behavior Sequence Endpoints

    Each item is available at an endpoint based on it's database ID: `/api/sequences/{id}/`.

    ## Filtering

    Behavior sequences can be filtered using a querystring parameter. Currently,
    filtering is availble for both goals and categories. You can filter by an
    ID or a slug.

    * Retrieve all *BehaviorSequence*s that belong to a particular goal:
      `/api/sequences/?goal={goal_id}` or by slug: `/api/sequences/?goal={goal_title_slug}`
    * Retrieve all *BehaviorSequence*s that belong to a particular category:
      `/api/sequences/?category={category_id}` or by slug:
      `/api/sequences/?category={category_title_slug}`

    ----

    """
    queryset = models.BehaviorSequence.objects.all()
    serializer_class = serializers.BehaviorSequenceSerializer

    def get_queryset(self):
        category = self.request.GET.get('category', None)
        goal = self.request.GET.get('goal', None)

        if category is not None and category.isnumeric():
            # Filter by Category.id
            self.queryset = self.queryset.filter(categories__id=category)
        elif category is not None:
            # Filter by Category.title_slug
            self.queryset = self.queryset.filter(categories__title_slug=category)

        if goal is not None and goal.isnumeric():
            # Filter by Goal.id
            self.queryset = self.queryset.filter(goals__id=goal)
        elif goal is not None:
            # Filter by Goal.title_slug
            self.queryset = self.queryset.filter(goals__title_slug=goal)

        return self.queryset


class BehaviorActionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.BehaviorAction.objects.all()
    serializer_class = serializers.BehaviorActionSerializer

    def get_queryset(self):
        if 'category' in self.request.GET:
            self.queryset = self.queryset.filter(
                sequence__categories__id=self.request.GET['category']
            )
        if 'goal' in self.request.GET:
            self.queryset = self.queryset.filter(
                sequence__goals__id=self.request.GET['goal']
            )
        if 'sequence' in self.request.GET:
            self.queryset = self.queryset.filter(
                sequence__id=self.request.GET['sequence']
            )
        return self.queryset
