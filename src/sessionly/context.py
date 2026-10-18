"""Wires configuration, database and services together for the UI."""

from __future__ import annotations

from dataclasses import dataclass

from sessionly.config import AppConfig
from sessionly.db import Database
from sessionly.services.automation import AutomationEngine, has_internet
from sessionly.services.meetings import MeetingService
from sessionly.services.links import LinkService
from sessionly.services.schedules import ScheduleService
from sessionly.services.sessions import SessionService
from sessionly.services.settings import SettingsService
from sessionly.services.voice_replies import VoiceReplyService


@dataclass
class AppContext:
    config: AppConfig
    db: Database
    meetings: MeetingService
    schedules: ScheduleService
    links: LinkService
    settings: SettingsService
    sessions: SessionService
    engine: AutomationEngine
    voice_replies: VoiceReplyService

    @classmethod
    def create(cls, config: AppConfig, db: Database, online=has_internet) -> AppContext:
        meetings, schedules, links = MeetingService(db), ScheduleService(db), LinkService(db)
        settings, sessions = SettingsService(db), SessionService(db)
        engine = AutomationEngine(meetings, schedules, links, sessions, settings, online=online)
        voice_replies = VoiceReplyService(db, config.data_dir / "voice")
        return cls(config, db, meetings, schedules, links, settings, sessions, engine, voice_replies)
