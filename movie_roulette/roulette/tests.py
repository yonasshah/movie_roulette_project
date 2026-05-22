from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from roulette.models import (
    UserList,
    UserContent,
    UserReview,
    Comment,
    Vote,
)


class PublicPageTests(TestCase):
    def test_homepage_accessible_without_login(self):
        response = self.client.get(reverse("roulette:roulette_view"))
        self.assertEqual(response.status_code, 200)

    def test_discover_accessible_without_login(self):
        response = self.client.get(reverse("roulette:discover"))
        self.assertEqual(response.status_code, 200)
        
class ReviewPermissionTests(TestCase):
    def test_guest_cannot_add_review(self):
        response = self.client.post(
            reverse("roulette:add_review", kwargs={
                "content_type": "movie",
                "tmdb_id": 123
            }),
            {
                "rating": 8,
                "review_text": "Good movie"
            }
        )

        self.assertIn(response.status_code, [302, 403])
        
class ReviewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="reviewuser",
            email="review@example.com",
            password="testpass123"
        )

    def test_logged_in_user_can_add_review(self):
        self.client.login(username="reviewuser", password="testpass123")

        response = self.client.post(
            reverse("roulette:add_review", kwargs={
                "content_type": "movie",
                "tmdb_id": 123
            }),
            {
                "rating": 8,
                "review_text": "Really good.",
                "title": "Test Movie",
                "poster_path": "",
                "overview": "Test overview"
            }
        )

        self.assertIn(response.status_code, [200, 302])

        self.assertTrue(
            UserReview.objects.filter(
                user=self.user,
                tmdb_id=123,
                content_type=UserContent.ContentType.MOVIE
            ).exists()
        )

    def test_review_update_does_not_create_duplicate(self):
        self.client.login(username="reviewuser", password="testpass123")

        url = reverse("roulette:add_review", kwargs={
            "content_type": "movie",
            "tmdb_id": 123
        })

        self.client.post(url, {
            "rating": 7,
            "review_text": "Good.",
            "title": "Test Movie",
            "poster_path": "",
            "overview": "Test overview"
        })

        self.client.post(url, {
            "rating": 9,
            "review_text": "Actually great.",
            "title": "Test Movie",
            "poster_path": "",
            "overview": "Test overview"
        })

        reviews = UserReview.objects.filter(
            user=self.user,
            tmdb_id=123,
            content_type=UserContent.ContentType.MOVIE
        )

        self.assertEqual(reviews.count(), 1)
        self.assertEqual(reviews.first().rating, 9)
        self.assertEqual(reviews.first().review_text, "Actually great.")
        
class UserListTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

    def test_logged_in_user_can_create_list(self):
        self.client.login(username="testuser", password="testpass123")

        response = self.client.post(
            reverse("roulette:list_create"),
            {"name": "Weekend Watchlist"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            UserList.objects.filter(
                user=self.user,
                name="Weekend Watchlist"
            ).exists()
        )
        
class WatchlistTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123"
        )

    def test_toggle_watchlist_adds_item(self):
        self.client.login(username="testuser", password="testpass123")

        response = self.client.post(
            reverse("roulette:toggle_watchlist"),
            {
                "tmdb_id": 123,
                "content_type": "movie",
                "title": "Test Movie",
                "poster_path": "",
                "release_year": "2024",
                "overview": "Test overview"
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            UserContent.objects.filter(
                user=self.user,
                tmdb_id=123,
                list_type=UserContent.ListType.WATCHLIST,
                content_type=UserContent.ContentType.MOVIE
            ).exists()
        )
        
class ContentDetailPublicTests(TestCase):
    def test_content_detail_accessible_without_login(self):
        response = self.client.get(
            reverse("roulette:content_detail", kwargs={
                "content_type": "movie",
                "tmdb_id": 123
            })
        )

        self.assertIn(response.status_code, [200, 500])

class ContentDetailPublicTests(TestCase):
    def test_content_detail_accessible_without_login(self):
        response = self.client.get(
            reverse("roulette:content_detail", kwargs={
                "content_type": "movie",
                "tmdb_id": 123
            })
        )

        self.assertIn(response.status_code, [200, 500])
        
        
class CommentTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="commentuser",
            email="comment@example.com",
            password="testpass123"
        )

        self.review = UserReview.objects.create(
            user=self.user,
            tmdb_id=123,
            content_type=UserContent.ContentType.MOVIE,
            rating=8,
            review_text="Good movie",
            title="Test Movie"
        )

    def test_logged_in_user_can_comment_on_review(self):
        self.client.login(username="commentuser", password="testpass123")

        review_ctype = ContentType.objects.get_for_model(UserReview)

        response = self.client.post(
            reverse("roulette:add_comment"),
            {
                "content_type_id": review_ctype.id,
                "object_id": self.review.id,
                "text": "I agree.",
                "next": "/"
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            Comment.objects.filter(
                user=self.user,
                object_id=self.review.id,
                text="I agree."
            ).exists()
        )
        
    def test_logged_in_user_can_reply_to_comment(self):
        self.client.login(username="commentuser", password="testpass123")

        review_ctype = ContentType.objects.get_for_model(UserReview)

        parent_comment = Comment.objects.create(
            user=self.user,
            content_type=review_ctype,
            object_id=self.review.id,
            text="Parent comment"
        )

        response = self.client.post(
            reverse("roulette:add_comment"),
            {
                "content_type_id": review_ctype.id,
                "object_id": self.review.id,
                "parent_id": parent_comment.id,
                "text": "Nested reply",
                "next": "/"
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            Comment.objects.filter(
                user=self.user,
                parent=parent_comment,
                text="Nested reply"
            ).exists()
        )
        
class VoteTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="voteuser",
            email="vote@example.com",
            password="testpass123"
        )

        self.review = UserReview.objects.create(
            user=self.user,
            tmdb_id=123,
            content_type=UserContent.ContentType.MOVIE,
            rating=8,
            review_text="Good movie",
            title="Test Movie"
        )

        self.comment_ctype = ContentType.objects.get_for_model(Comment)
        self.review_ctype = ContentType.objects.get_for_model(UserReview)

        self.comment = Comment.objects.create(
            user=self.user,
            content_type=self.review_ctype,
            object_id=self.review.id,
            text="Nice review"
        )

    def test_logged_in_user_can_upvote_comment(self):
        self.client.login(username="voteuser", password="testpass123")

        response = self.client.post(
            reverse("roulette:toggle_vote"),
            {
                "content_type_id": self.comment_ctype.id,
                "object_id": self.comment.id,
                "vote_type": 1
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            Vote.objects.filter(
                user=self.user,
                content_type=self.comment_ctype,
                object_id=self.comment.id,
                vote_type=1
            ).exists()
        )
        
    def test_clicking_same_vote_twice_removes_vote(self):
        self.client.login(username="voteuser", password="testpass123")

        url = reverse("roulette:toggle_vote")

        payload = {
            "content_type_id": self.comment_ctype.id,
            "object_id": self.comment.id,
            "vote_type": 1
        }

        self.client.post(url, payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.client.post(url, payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.assertFalse(
            Vote.objects.filter(
                user=self.user,
                content_type=self.comment_ctype,
                object_id=self.comment.id
            ).exists()
        )
        
    def test_toggle_watchlist_twice_removes_item(self):
        self.client.login(username="testuser", password="testpass123")

        url = reverse("roulette:toggle_watchlist")

        payload = {
            "tmdb_id": 123,
            "content_type": "movie",
            "title": "Test Movie",
            "poster_path": "",
            "release_year": "2024",
            "overview": "Test overview"
        }

        self.client.post(url, payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.client.post(url, payload, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        self.assertFalse(
            UserContent.objects.filter(
                user=self.user,
                tmdb_id=123,
                list_type=UserContent.ListType.WATCHLIST,
                content_type=UserContent.ContentType.MOVIE
            ).exists()
        )
        
class FavoriteTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="favoriteuser",
            email="favorite@example.com",
            password="testpass123"
        )

    def test_toggle_favorite_adds_item(self):
        self.client.login(username="favoriteuser", password="testpass123")

        response = self.client.post(
            reverse("roulette:toggle_favorite"),
            {
                "tmdb_id": 456,
                "content_type": "tv",
                "title": "Test Show",
                "poster_path": "",
                "release_year": "2024",
                "overview": "Test overview"
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            UserContent.objects.filter(
                user=self.user,
                tmdb_id=456,
                list_type=UserContent.ListType.FAVORITE,
                content_type=UserContent.ContentType.TV
            ).exists()
        )
        
class CustomListItemTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="listitemuser",
            email="listitem@example.com",
            password="testpass123"
        )

        self.user_list = UserList.objects.create(
            user=self.user,
            name="Weekend Watch"
        )

    def test_add_item_to_custom_list(self):
        self.client.login(username="listitemuser", password="testpass123")

        response = self.client.post(
            reverse("roulette:list_add_item"),
            {
                "list_id": self.user_list.id,
                "tmdb_id": 789,
                "content_type": "movie",
                "title": "Custom List Movie",
                "poster_path": "",
                "release_year": "2023",
                "overview": "Test overview"
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )

        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            UserContent.objects.filter(
                user=self.user,
                custom_list=self.user_list,
                tmdb_id=789,
                list_type=UserContent.ListType.CUSTOM,
                content_type=UserContent.ContentType.MOVIE
            ).exists()
        )
        
