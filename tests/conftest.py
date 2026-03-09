import pytest

from feishu_notify.config import NotifyConfig
from feishu_notify.core.types import LinkButton, NotifyLevel, NotifyMessage


@pytest.fixture
def sample_message():
    return NotifyMessage(
        level=NotifyLevel.ERROR,
        title="Test Error",
        content="Something went wrong",
        source="test-suite",
        task_name="test_task",
        error_msg="NullPointerException",
    )


@pytest.fixture
def sample_config():
    return NotifyConfig(
        webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/test-hook",
        default_source="test",
    )


@pytest.fixture
def full_message():
    return NotifyMessage(
        level=NotifyLevel.CRITICAL,
        title="Critical Alert",
        content="Production is down",
        source="Airflow",
        task_name="sync_job",
        task_id="task_001",
        start_time="2024-01-15 10:00:00",
        end_time="2024-01-15 10:15:00",
        duration="15min",
        error_msg="Connection refused",
        error_code="ERR_001",
        metrics={"rows": 15000, "tables": 3},
        links=[LinkButton(text="View Log", url="https://example.com/log")],
        mentions=["user123"],
        mention_all=True,
        dedupe_key="unique-key",
        extra={"env": "production"},
    )
