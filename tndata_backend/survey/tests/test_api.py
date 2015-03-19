from django.contrib.auth import get_user_model
from django.core.urlresolvers import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .. models import (
    LikertQuestion,
    LikertResponse,
    MultipleChoiceQuestion,
    MultipleChoiceResponse,
    MultipleChoiceResponseOption,
    OpenEndedQuestion,
    OpenEndedResponse,
)


class TestLikertQuestionAPI(APITestCase):

    def setUp(self):
        self.question = LikertQuestion.objects.create(text='Test Question')

    def tearDown(self):
        LikertQuestion.objects.filter(id=self.question.id).delete()

    def test_get_list(self):
        url = reverse('likertquestion-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['count'], 1)
        c = response.data['results'][0]
        self.assertEqual(c['id'], self.question.id)
        self.assertEqual(c['order'], self.question.order)
        self.assertEqual(c['text'], self.question.text)
        self.assertEqual(c['available'], self.question.available)
        self.assertEqual(c['updated'], self.question.updated)
        self.assertEqual(c['created'], self.question.created)

    def test_post_list(self):
        """Ensure this endpoint is read-only."""
        url = reverse('likertquestion-list')
        response = self.client.post(url, {})
        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def test_get_detail(self):
        """Ensure this endpoint provides question detail info."""
        url = reverse('likertquestion-detail', args=[self.question.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.question.id)

    def test_post_detail(self):
        """Ensure this endpoint is read-only."""
        url = reverse('likertquestion-detail', args=[self.question.id])
        response = self.client.post(url, {})
        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED
        )


class TestOpenEndedQuestionAPI(APITestCase):

    def setUp(self):
        self.question = OpenEndedQuestion.objects.create(text='Test Question')

    def tearDown(self):
        OpenEndedQuestion.objects.filter(id=self.question.id).delete()

    def test_get_list(self):
        url = reverse('openendedquestion-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['count'], 1)
        c = response.data['results'][0]
        self.assertEqual(c['id'], self.question.id)
        self.assertEqual(c['order'], self.question.order)
        self.assertEqual(c['text'], self.question.text)
        self.assertEqual(c['available'], self.question.available)
        self.assertEqual(c['updated'], self.question.updated)
        self.assertEqual(c['created'], self.question.created)

    def test_post_list(self):
        """Ensure this endpoint is read-only."""
        url = reverse('openendedquestion-list')
        response = self.client.post(url, {})
        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def test_get_detail(self):
        """Ensure this endpoint provides question detail info."""
        url = reverse('openendedquestion-detail', args=[self.question.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.question.id)

    def test_post_detail(self):
        """Ensure this endpoint is read-only."""
        url = reverse('openendedquestion-detail', args=[self.question.id])
        response = self.client.post(url, {})
        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED
        )


class TestMultipleChoiceQuestionAPI(APITestCase):

    def setUp(self):
        self.question = MultipleChoiceQuestion.objects.create(
            text='Test Question'
        )
        self.option = MultipleChoiceResponseOption.objects.create(
            question=self.question,
            text="Test Option",
            available=True
        )

    def tearDown(self):
        MultipleChoiceQuestion.objects.filter(id=self.question.id).delete()
        MultipleChoiceResponseOption.objects.filter(id=self.option.id).delete()

    def test_get_list(self):
        url = reverse('multiplechoicequestion-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['count'], 1)
        c = response.data['results'][0]
        self.assertEqual(c['id'], self.question.id)
        self.assertEqual(c['order'], self.question.order)
        self.assertEqual(c['text'], self.question.text)
        self.assertEqual(c['available'], self.question.available)
        self.assertEqual(c['updated'], self.question.updated)
        self.assertEqual(c['created'], self.question.created)
        # Make sure the question has a list of option(s)
        self.assertIn("options", c)
        self.assertEqual(c['options'][0]['id'], self.option.id)
        self.assertEqual(c['options'][0]['text'], self.option.text)

    def test_post_list(self):
        """Ensure this endpoint is read-only."""
        url = reverse('multiplechoicequestion-list')
        response = self.client.post(url, {})
        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED
        )

    def test_get_detail(self):
        """Ensure this endpoint provides question detail info."""
        url = reverse('multiplechoicequestion-detail', args=[self.question.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.question.id)
        self.assertIn("options", response.data)
        self.assertEqual(response.data['options'][0]['id'], self.option.id)
        self.assertEqual(response.data['options'][0]['text'], self.option.text)

    def test_post_detail(self):
        """Ensure this endpoint is read-only."""
        url = reverse('multiplechoicequestion-detail', args=[self.question.id])
        response = self.client.post(url, {})
        self.assertEqual(
            response.status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED
        )


class TestLikertResponseAPI(APITestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create(
            username="test",
            email="test@example.com",
        )
        self.question = LikertQuestion.objects.create(text="Test Question")
        self.response = LikertResponse.objects.create(
            user=self.user,
            question=self.question,
            selected_option=1
        )

    def tearDown(self):
        User = get_user_model()
        User.objects.filter(id=self.user.id).delete()
        LikertQuestion.objects.filter(id=self.question.id).delete()
        LikertResponse.objects.filter(id=self.response.id).delete()

    def test_get_list_unauthenticated(self):
        """Ensure un-authenticated requests don't expose any results."""
        url = reverse('likertresponse-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_get_list_authenticated(self):
        """Ensure authenticated requests DO expose results."""
        url = reverse('likertresponse-list')
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.response.id)
        self.assertEqual(response.data['results'][0]['user'], self.user.id)
        self.assertEqual(
            response.data['results'][0]['question']['id'],
            self.question.id
        )

    def test_post_list_unathenticated(self):
        """Unauthenticated requests should not be allowed to post new
        LikertResponses"""
        url = reverse('likertresponse-list')
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_list_athenticated(self):
        """Authenticated users should be able to create a LikertResponse."""
        q = LikertQuestion.objects.create(text="New Question")

        url = reverse('likertresponse-list')
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        data = {"question": q.id, 'selected_option': 1}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(LikertResponse.objects.filter(user=self.user).count(), 2)
        q.delete()  # Clean up.

    def test_get_detail_unauthed(self):
        """Ensure unauthenticated users cannot view this endpoint."""
        url = reverse('likertresponse-detail', args=[self.response.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_detail(self):
        """Ensure authenticated users can view this endpoint."""
        url = reverse('likertresponse-detail', args=[self.response.id])
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_post_detail_not_allowed(self):
        """Ensure POSTing to the detail endpoint is not allowed."""
        url = reverse('likertresponse-detail', args=[self.response.id])
        response = self.client.post(url, {'question': 1, 'selected_option': 1})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Even if you're authenticated
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        response = self.client.post(url, {'question': 1, 'selected_option': 1})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_put_detail_not_allowed(self):
        """Ensure PUTing to the detail endpoint is not allowed."""
        url = reverse('likertresponse-detail', args=[self.response.id])
        response = self.client.put(url, {'question': 1, 'selected_option': 1})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Even if you're authenticated
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        response = self.client.put(url, {'question': 1, 'selected_option': 1})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_not_allowed(self):
        """Ensure DELETEing is not allowed.."""
        url = reverse('likertresponse-detail', args=[self.response.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Even if you're authenticated
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class TestOpenEndedResponseAPI(APITestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create(
            username="test",
            email="test@example.com",
        )
        self.question = OpenEndedQuestion.objects.create(text="Test Question")
        self.response = OpenEndedResponse.objects.create(
            user=self.user,
            question=self.question,
            response="Test Response"
        )

    def tearDown(self):
        User = get_user_model()
        User.objects.filter(id=self.user.id).delete()
        OpenEndedQuestion.objects.filter(id=self.question.id).delete()
        OpenEndedResponse.objects.filter(id=self.response.id).delete()

    def test_get_list_unauthenticated(self):
        """Ensure un-authenticated requests don't expose any results."""
        url = reverse('openendedresponse-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_get_list_authenticated(self):
        """Ensure authenticated requests DO expose results."""
        url = reverse('openendedresponse-list')
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.response.id)
        self.assertEqual(response.data['results'][0]['user'], self.user.id)
        self.assertEqual(
            response.data['results'][0]['question']['id'],
            self.question.id
        )

    def test_post_list_unathenticated(self):
        """Unauthenticated requests should not be allowed to post new
        OpenEndedResponses"""
        url = reverse('openendedresponse-list')
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_list_athenticated(self):
        """Authenticated users should be able to create a OpenEndedResponse."""
        q = OpenEndedQuestion.objects.create(text="New Question")

        url = reverse('openendedresponse-list')
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        data = {"question": q.id, 'response': 7}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(OpenEndedResponse.objects.filter(user=self.user).count(), 2)
        q.delete()  # Clean up.

    def test_get_detail_unauthed(self):
        """Ensure unauthenticated users cannot view this endpoint."""
        url = reverse('openendedresponse-detail', args=[self.response.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_detail(self):
        """Ensure authenticated users can view this endpoint."""
        url = reverse('openendedresponse-detail', args=[self.response.id])
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_post_detail_not_allowed(self):
        """Ensure POSTing to the detail endpoint is not allowed."""
        url = reverse('openendedresponse-detail', args=[self.response.id])
        response = self.client.post(url, {'question': 1, 'response': 7})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Even if you're authenticated
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        response = self.client.post(url, {'question': 1, 'response': 7})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_put_detail_not_allowed(self):
        """Ensure PUTing to the detail endpoint is not allowed."""
        url = reverse('openendedresponse-detail', args=[self.response.id])
        response = self.client.put(url, {'question': 1, 'response': 7})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Even if you're authenticated
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        response = self.client.put(url, {'question': 1, 'response': 7})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_not_allowed(self):
        """Ensure DELETEing is not allowed.."""
        url = reverse('openendedresponse-detail', args=[self.response.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Even if you're authenticated
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class TestMultipleChoiceResponseAPI(APITestCase):

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create(
            username="test",
            email="test@example.com",
        )
        self.question = MultipleChoiceQuestion.objects.create(
            text="Test Question"
        )
        self.option = MultipleChoiceResponseOption.objects.create(
            question=self.question,
            text="Option 1",
            available=True,
        )
        self.response = MultipleChoiceResponse.objects.create(
            user=self.user,
            question=self.question,
            selected_option=self.option,
        )

    def tearDown(self):
        User = get_user_model()
        User.objects.filter(id=self.user.id).delete()
        MultipleChoiceQuestion.objects.filter(id=self.question.id).delete()
        MultipleChoiceResponse.objects.filter(id=self.response.id).delete()
        MultipleChoiceResponseOption.objects.filter(id=self.option.id).delete()

    def test_get_list_unauthenticated(self):
        """Ensure un-authenticated requests don't expose any results."""
        url = reverse('multiplechoiceresponse-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_get_list_authenticated(self):
        """Ensure authenticated requests DO expose results."""
        url = reverse('multiplechoiceresponse-list')
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.response.id)
        self.assertEqual(response.data['results'][0]['user'], self.user.id)
        self.assertEqual(
            response.data['results'][0]['question']['id'],
            self.question.id
        )

    def test_post_list_unathenticated(self):
        """Unauthenticated requests should not be allowed to post new
        MultipleChoiceResponses"""
        url = reverse('multiplechoiceresponse-list')
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_list_athenticated(self):
        """Authenticated users should be able to create a
        MultipleChoiceResponse."""
        q = MultipleChoiceQuestion.objects.create(text="New Question")
        o = MultipleChoiceResponseOption.objects.create(question=q, text="A")

        url = reverse('multiplechoiceresponse-list')
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        data = {"question": q.id, 'selected_option': o.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            MultipleChoiceResponse.objects.filter(user=self.user).count(),
            2
        )

        # Clean up.
        q.delete()
        o.delete()

    def test_get_detail_unauthed(self):
        """Ensure unauthenticated users cannot view this endpoint."""
        url = reverse('multiplechoiceresponse-detail', args=[self.response.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_detail(self):
        """Ensure authenticated users can view this endpoint."""
        url = reverse('multiplechoiceresponse-detail', args=[self.response.id])
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_post_detail_not_allowed(self):
        """Ensure POSTing to the detail endpoint is not allowed."""
        url = reverse('multiplechoiceresponse-detail', args=[self.response.id])
        data = {'question': 1, 'selected_option': self.option.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Even if you're authenticated
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        data = {'question': 1, 'selected_option': self.option.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_put_detail_not_allowed(self):
        """Ensure PUTing to the detail endpoint is not allowed."""
        url = reverse('multiplechoiceresponse-detail', args=[self.response.id])
        data = {'question': 1, 'selected_option': self.option.id}
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Even if you're authenticated
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        data = {'question': 1, 'selected_option': self.option.id}
        response = self.client.put(url, data)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_not_allowed(self):
        """Ensure DELETEing is not allowed.."""
        url = reverse('multiplechoiceresponse-detail', args=[self.response.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # Even if you're authenticated
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.user.auth_token.key
        )
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
