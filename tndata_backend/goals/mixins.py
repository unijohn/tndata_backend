"""
This module contains Mixins.

"""
from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.contrib.staticfiles.templatetags.staticfiles import static
from django.core.exceptions import ImproperlyConfigured
from django.core.urlresolvers import reverse

from rest_framework import status
from rest_framework.response import Response

from . permissions import superuser_required, is_content_author, is_content_editor


# Mixins for Views
# ----------------

class DeleteMultipleMixin:
    """A Mixin that allows deleting multiple objects when a DELETE request is
    sent with a list of modelnames and object IDs.

    """
    def delete(self, request, *args, **kwargs):
        # TODO: why is auth not getting handled by the authentication_classes, here?

        model = self.get_queryset().model
        model_name = model.__name__.lower()

        if isinstance(request.data, list) and request.user.is_authenticated():
            # We're deleting multiple items; just assume they exist?
            params = {
                "pk__in": filter(None, (d[model_name] for d in request.data)),
                "user": request.user.id,
            }
            model.objects.filter(**params).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(status=status.HTTP_400_BAD_REQUEST)


class SuperuserRequiredMixin:
    """A Mixin that requires the user to be a superuser in order to access
    the view.
    """
    @classmethod
    def as_view(cls, **initkwargs):
        view = super(SuperuserRequiredMixin, cls).as_view(**initkwargs)
        dec = user_passes_test(superuser_required, login_url=settings.LOGIN_URL)
        return dec(view)


class ContentAuthorMixin:
    """A Mixin that requires the user to be in the 'Content Authors' group."""
    @classmethod
    def as_view(cls, **initkwargs):
        view = super(ContentAuthorMixin, cls).as_view(**initkwargs)
        dec = user_passes_test(is_content_author, login_url=settings.LOGIN_URL)
        return dec(view)


class ContentEditorMixin:
    """A Mixin that requires the user to be in the 'Content Editors' group."""
    @classmethod
    def as_view(cls, **initkwargs):
        view = super(ContentEditorMixin, cls).as_view(**initkwargs)
        dec = user_passes_test(is_content_editor, login_url=settings.LOGIN_URL)
        return dec(view)


# Mixins for Models
# -----------------

class ModifiedMixin:
    def _check_updated_or_created_by(self, **kwargs):
        """Allows passing `updated_by` or `created_by` paramters in a model's
        save() method.

        USAGE: override `save` in a model and call:

            _check_updated_or_created_by(**kwargs)

        """
        updated_by = kwargs.pop("updated_by", None)
        if updated_by:
            self.updated_by = updated_by
        created_by = kwargs.pop("created_by", None)
        if created_by:
            self.created_by = created_by
        return kwargs


class URLMixin:
    """Contains methods for reversing Model URLs. This Mixin DRYs up the various
    get_XXXX_url methods that I use on models, particularly for Read, Update,
    and Delete actions.

    Models using this mixin can customize its behavior by specifying the
    following:

    * (required) urls_app_namespace: The url namespace used for the app
    * (required) urls_model_name: The model name used for the url
    * urls_slug_field: The unique slug used for the model. Default is `title_slug`
    * urls_icon_field: An icon field for the model. Defaut is None.
    * urls_image_field: An image field for the model. Defaut is None.

    This mixin also supports a default icon or image as a static file. To use
    this, just set one of the following:

    * default_icon:  e.g. `default_icon = "img/grow-icon.png"`
    * default_image

    And we make the assumption that we have the following URLs defined, e.g.
    for the Category model:

    * Read: category-detail
    * Update: category-update
    * Delete: category-delete

    """
    urls_app_namespace = None  # e.g. 'goals'
    urls_model_name = None  # e.g. 'category'
    urls_slug_field = "title_slug"  # e.g. 'name_slug', if different.
    urls_icon_field = None
    urls_image_field = None

    # Support for default icons/images as a static file
    default_icon = None
    default_image = None

    def _slug_field(self):
        return getattr(self, self.urls_slug_field, None)

    def _view(self, view_name):
        if self.urls_app_namespace is None or self.urls_model_name is None:
            raise ImproperlyConfigured(
                "Models using URLMixin must define both urls_app_namespace and "
                "urls_model_name."
            )
        return "{0}:{1}-{2}".format(
            self.urls_app_namespace, self.urls_model_name, view_name
        )

    def get_absolute_url(self):
        return reverse(self._view('detail'), args=[self._slug_field()])

    def get_publish_url(self):
        return reverse(self._view('publish'), args=[self._slug_field()])

    def get_update_url(self):
        return reverse(self._view('update'), args=[self._slug_field()])

    def get_delete_url(self):
        return reverse(self._view('delete'), args=[self._slug_field()])

    def get_absolute_icon(self):
        icon_field = getattr(self, self.urls_icon_field, None)
        if self.urls_icon_field and icon_field:
            return icon_field.url
        elif self.default_icon:
            return static(self.default_icon)

    def get_absolute_image(self):
        image_field = getattr(self, self.urls_image_field, None)
        if self.urls_image_field and image_field:
            return image_field.url
        elif self.default_image:
            return static(self.default_image)
