"""
These views are for internal organizational use.

"""
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.generic import View, TemplateView
from django.views.generic.detail import DetailView

from . models import Rule
from . import rulesets


def _authenticated_and_staff(user):
    """A test function for use witht he user_passes_test decorator.
    Verifies that a user is both authenticated and staff."""
    return user.is_authenticated() and user.is_staff


class AdminRequiredMixin(object):
    """A Mixin that uses `_authenticated_and_staff` to restrict access to
    users who meet both criteria."""
    @classmethod
    def as_view(cls, **initkwargs):
        view = super(AdminRequiredMixin, cls).as_view(**initkwargs)
        decor = user_passes_test(_authenticated_and_staff, login_url='/admin/')
        return decor(view)


class RulesDataView(View):
    http_method_names = ['get', 'head']

    def get(self, request):
        return JsonResponse(rulesets.ruleset.export())


class AddRuleView(AdminRequiredMixin, TemplateView):
    template_name = 'rules/rules.html'


class RulesView(AdminRequiredMixin, View):
    http_method_names = ['get', 'head', 'post']

    def get(self, request):
        context = {
            'rules': Rule.objects.all()
        }
        return render(request, 'rules/index.html', context)

    def post(self, request, *args, **kwargs):
        """Create a new Rule using data from the business-rules-ui plugin.
        TODO: We probably need a form for this, but this'll do for now."""

        rule = Rule.objects.create(
            app_name=request.POST['app_name'],
            rule_name=request.POST['rule_name'],
            conditions=request.POST['conditions'],
            actions=request.POST['actions'],
        )
        messages.success(request, "Created: {0}".format(rule))
        if request.is_ajax():
            return JsonResponse({})
        return redirect("rules:rules")


class RuleDetailView(AdminRequiredMixin, DetailView):
    model = Rule

    def post(self, request, *args, **kwargs):
        """DELETE a rule. It's still do hard to build a `delete` method :(
        This is currently only
        """
        obj = self.get_object()
        messages.success(request, "Deleted: {0}".format(obj))
        obj.delete()
        if request.is_ajax():
            return JsonResponse({})
        return redirect("rules:rules")
