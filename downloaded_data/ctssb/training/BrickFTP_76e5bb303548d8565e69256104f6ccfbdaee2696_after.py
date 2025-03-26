from pathlib import Path
import os
from json.decoder import JSONDecodeError

from requests.exceptions import RequestException
import pytest

from brickftp import BrickFTP, BrickFTPError

BRICK_FTP_USER = os.environ['BRICK_FTP_USER']
BRICK_FTP_PASS = os.environ['BRICK_FTP_PASS']
BRICK_FTP_SUBDOMAIN = os.environ['BRICK_FTP_SUBDOMAIN']
BASE_DIR = 'Test Folder'


@pytest.fixture
def client():
    client = BrickFTP(
        username=BRICK_FTP_USER,
        password=BRICK_FTP_PASS,
        subdomain=BRICK_FTP_SUBDOMAIN,
    )
    paths = (i['path'] for i in client.dir(BASE_DIR))
    for path in paths:
        client.delete(path)
    yield client


def test_login(client):
    client._login()


def test_login_with_invalid_creds():
    client = BrickFTP(username='aaa', password='aaa', subdomain='aaa')
    with pytest.raises(BrickFTPError):
        client._login()


def test_dir(client):
    resp_json = client.dir('/')

    assert isinstance(resp_json, list)
    assert len(resp_json) >= 1


def test_mkdir(client):
    path = Path(BASE_DIR, 'cheat codes')
    resp_json = client.mkdir(path)

    assert resp_json == []

    resp_json = client.dir(path)
    assert resp_json == []


def test_folders(client, mocker):
    client.upload(
        upload_path=Path(BASE_DIR, 'data.txt'),
        local_path=Path(Path(__file__).parent, 'data.txt'),
    )
    resp_json = client.dir(BASE_DIR)

    assert len(resp_json) > 0
    for item in resp_json:
        exp_item_keys = (
            'crc32', 'display_name', 'id', 'md5', 'mtime', 'path',
            'permissions', 'provided_mtime', 'size', 'type'
        )
        assert isinstance(item, dict)
        assert set(exp_item_keys).issubset(item.keys())


def test_upload(client):
    client.upload(
        upload_path=str(Path(BASE_DIR, 'data.txt')),
        local_path=Path(Path(__file__).parent, 'data.txt'),
    )

    resp_json = client.dir(BASE_DIR)
    assert f'{BASE_DIR}/data.txt' in [i['path'] for i in resp_json]


def test_download(client):
    upload_path = Path(BASE_DIR, 'data2.txt')
    client.upload(
        upload_path=upload_path,
        local_path=Path(Path(__file__).parent, 'data.txt'),
    )

    downloaded_path = client.download_file(
        remote_path=upload_path, local_path='/tmp/data2.txt'
    )

    assert downloaded_path == '/tmp/data2.txt'
    assert os.path.isfile('/tmp/data2.txt')


def test_download_without_local_path(client):
    upload_path = Path(BASE_DIR, 'data2.txt')
    client.upload(
        upload_path=upload_path,
        local_path=Path(Path(__file__).parent, 'data.txt'),
    )

    downloaded_path = Path(client.download_file(remote_path=upload_path))

    # Check the downloaded filename is readable and similar to the remote
    assert downloaded_path.name.endswith('.txt')
    assert downloaded_path.name.startswith('data2')
    assert os.path.isfile(downloaded_path)


def test_download_without_local_path_generates_local_path(client):
    upload_path = Path(BASE_DIR, 'data2.txt')
    client.upload(
        upload_path=upload_path,
        local_path=Path(Path(__file__).parent, 'data.txt'),
    )

    downloaded_path = client.download_file(remote_path=upload_path)

    assert os.path.isfile(downloaded_path)


def test_delete(client):
    upload_path = Path(BASE_DIR, 'data.txt')
    client.upload(
        upload_path=upload_path,
        local_path=Path(Path(__file__).parent, 'data.txt'),
    )

    client.delete(upload_path)

    assert len(client.dir(BASE_DIR)) == 0


def test_raises_brickftperror_when_response_is_not_valid_json(client, mocker):
    mock_requests = mocker.patch('brickftp.client.requests')
    mock_requests.get().json.side_effect = JSONDecodeError(
        msg='', doc=mocker.MagicMock(), pos=1
    )

    with pytest.raises(BrickFTPError) as exc:
        client.dir('/')

    exc.match(r'Non-valid JSON response:.+')


def test_raises_brickftperror_when_connectionerror(client, mocker):
    mock_requests = mocker.patch('brickftp.client.requests')
    mock_requests.get.side_effect = RequestException('msg')

    with pytest.raises(BrickFTPError) as exc:
        client.dir('/')

    exc.match(r'msg')
