from django import template
from django.contrib.contenttypes.models import ContentType
from roulette.models import Comment

register = template.Library()

@register.simple_tag
def get_comment_ctype_id():
    """Returns the ContentType ID for the Comment model, used for voting on comments."""
    return ContentType.objects.get_for_model(Comment).id