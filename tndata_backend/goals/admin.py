from django.contrib import admin
from . import models

from utils.admin import UserRelatedModelAdmin


class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'title_slug', 'order', 'get_absolute_icon',
        'created_by', 'created_on', 'updated_by', 'updated_on',
    )
    search_fields = ['title', 'description', 'notes']
    prepopulated_fields = {"title_slug": ("title", )}

admin.site.register(models.Category, CategoryAdmin)


class GoalAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'title_slug', 'in_categories', 'get_absolute_icon',
        'created_by', 'created_on', 'updated_by', 'updated_on',
    )
    search_fields = ['title', 'subtitle', 'description', 'outcome']
    prepopulated_fields = {"title_slug": ("title", )}

    def in_categories(self, obj):
        return ", ".join(sorted([cat.title for cat in obj.categories.all()]))

admin.site.register(models.Goal, GoalAdmin)


class TriggerAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'trigger_type', 'frequency', 'time', 'date', 'location',
    )
    prepopulated_fields = {"name_slug": ("name", )}
admin.site.register(models.Trigger, TriggerAdmin)


class BehaviorAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'in_categories', 'in_goals',
        'get_absolute_icon', 'get_absolute_image',
        'created_by', 'created_on', 'updated_by', 'updated_on',
    )
    search_fields = [
        'title', 'source_notes', 'notes', 'narrative_block', 'description',
        'case', 'outcome', 'notification_text',
    ]
    prepopulated_fields = {"title_slug": ("title", )}

    def in_categories(self, obj):
        return ", ".join(sorted([cat.title for cat in obj.categories.all()]))

    def in_goals(self, obj):
        return ", ".join(sorted([g.title for g in obj.goals.all()]))
admin.site.register(models.Behavior, BehaviorAdmin)


class ActionAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'behavior', 'sequence_order',
        'get_absolute_icon', 'get_absolute_image',
        'created_by', 'created_on', 'updated_by', 'updated_on',
    )
    search_fields = [
        'title', 'source_notes', 'notes', 'narrative_block', 'description',
        'case', 'outcome', 'notification_text',
    ]
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
