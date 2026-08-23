from unittest import mock

import pytest

from app.services import story_factory


def _story(word_count: int) -> str:
    return " ".join(f"word{index}" for index in range(word_count))


def test_story_length_contract_accepts_only_100_to_115_words():
    assert story_factory.validate_story_length(_story(100)) == 100
    assert story_factory.validate_story_length(_story(115)) == 115
    with pytest.raises(story_factory.StoryLengthError):
        story_factory.validate_story_length(_story(99))
    with pytest.raises(story_factory.StoryLengthError):
        story_factory.validate_story_length(_story(116))


def test_category_is_random_unless_explicitly_requested():
    rng = mock.Mock()
    rng.choice.return_value = "a time loop with one changing detail"
    assert story_factory.choose_category(None, rng=rng) == (
        "a time loop with one changing detail"
    )
    rng.choice.assert_called_once_with(story_factory.STORY_CATEGORIES)
    assert story_factory.choose_category("custom category", rng=rng) == "custom category"


def test_semantically_similar_embedding_is_rejected():
    with pytest.raises(story_factory.DuplicateStoryError):
        story_factory.reject_if_similar(
            [1.0, 0.0], [[0.99, 0.01], [0.0, 1.0]], threshold=0.95
        )


def test_repository_without_database_keeps_local_development_usable():
    embedding_factory = mock.Mock(side_effect=AssertionError("must not be called"))
    repository = story_factory.StoryRepository(
        database_url="", embedding_factory=embedding_factory
    )
    record = repository.reserve_story(
        task_id="task-1",
        category="mystery",
        subject="anything",
        script=_story(105),
    )
    assert record.word_count == 105
    embedding_factory.assert_not_called()
