from unittest import mock

from app.services import youtube_publisher


def test_upload_is_always_private_before_approval():
    request = mock.Mock()
    request.next_chunk.return_value = (None, {"id": "youtube-1"})
    videos = mock.Mock()
    videos.insert.return_value = request
    client = mock.Mock()
    client.videos.return_value = videos

    with (
        mock.patch.object(youtube_publisher, "_client", return_value=client),
        mock.patch(
            "googleapiclient.http.MediaFileUpload", return_value=mock.Mock()
        ),
    ):
        result = youtube_publisher.upload_private(
            ["final.mp4"], title="Fiction #Shorts"
        )

    assert result == ["youtube-1"]
    body = videos.insert.call_args.kwargs["body"]
    assert body["status"]["privacyStatus"] == "private"
    assert body["status"]["containsSyntheticMedia"] is True


def test_publish_only_changes_known_private_video_ids_to_public():
    update_request = mock.Mock()
    videos = mock.Mock()
    videos.update.return_value = update_request
    client = mock.Mock()
    client.videos.return_value = videos
    with mock.patch.object(youtube_publisher, "_client", return_value=client):
        youtube_publisher.publish(["youtube-1"])

    body = videos.update.call_args.kwargs["body"]
    assert body["id"] == "youtube-1"
    assert body["status"]["privacyStatus"] == "public"
    update_request.execute.assert_called_once_with()
