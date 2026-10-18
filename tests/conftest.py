import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # no windows pop up during tests

import pytest

from sessionly.db import open_database
from sessionly.services.meetings import MeetingService
from sessionly.services.links import LinkService
from sessionly.services.schedules import ScheduleService
from sessionly.services.settings import SettingsService


@pytest.fixture
def db(tmp_path):
    database = open_database(tmp_path / "test.db")
    yield database
    database.close()


@pytest.fixture
def meetings(db):
    return MeetingService(db)


@pytest.fixture
def schedules(db):
    return ScheduleService(db)


@pytest.fixture
def links(db):
    return LinkService(db)


@pytest.fixture
def settings(db):
    return SettingsService(db)
