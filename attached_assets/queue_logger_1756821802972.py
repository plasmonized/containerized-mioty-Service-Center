"""Queue monitoring and logging utilities."""

import asyncio
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class QueueLogger:
    """Monitor and log queue statistics."""

    def __init__(self, name: str, queue: asyncio.Queue) -> None:
        """Initialize queue logger."""
        self.name = name
        self.queue = queue
        self.max_size_seen = 0
        self.total_items_processed = 0
        self.peak_size_timestamp = None

    def update_stats(self) -> None:
        """Update queue statistics."""
        current_size = self.queue.qsize()
        if current_size > self.max_size_seen:
            self.max_size_seen = current_size
            self.peak_size_timestamp = asyncio.get_event_loop().time()

    def get_stats(self) -> Dict[str, Any]:
        """Get current queue statistics."""
        self.update_stats()
        return {
            "name": self.name,
            "current_size": self.queue.qsize(),
            "max_size_seen": self.max_size_seen,
            "total_processed": self.total_items_processed,
            "peak_timestamp": self.peak_size_timestamp,
        }

    def log_stats(self) -> None:
        """Log current queue statistics."""
        stats = self.get_stats()
        logger.info(
            f"Queue '{self.name}': current={stats['current_size']}, "
            f"max={stats['max_size_seen']}, "
            f"processed={stats['total_processed']}"
        )


def setup_queue_logging(queues: Dict[str, asyncio.Queue]) -> Dict[str, QueueLogger]:
    """
    Set up queue logging for multiple queues.

    Args:
        queues: Dictionary mapping queue names to queue objects

    Returns:
        Dictionary mapping queue names to QueueLogger instances
    """
    queue_loggers = {}

    for name, queue in queues.items():
        queue_logger = QueueLogger(name, queue)
        queue_loggers[name] = queue_logger
        logger.info(f"📊 Queue logger initialized for '{name}' (ID: {id(queue)})")

    return queue_loggers


def log_all_queue_stats(queue_loggers: Dict[str, QueueLogger]) -> None:
    """
    Log statistics for all monitored queues.

    Args:
        queue_loggers: Dictionary of QueueLogger instances
    """
    logger.info("📊 QUEUE STATISTICS REPORT:")
    logger.info("=" * 50)

    for name, queue_logger in queue_loggers.items():
        queue_logger.log_stats()

    logger.info("=" * 50)


async def monitor_queue_health(
    queue_loggers: Dict[str, QueueLogger],
    check_interval: int = 300,
    warning_threshold: int = 100,
) -> None:
    """
    Monitor queue health and log warnings for large queues.

    Args:
        queue_loggers: Dictionary of QueueLogger instances
        check_interval: How often to check (seconds)
        warning_threshold: Queue size threshold for warnings
    """
    logger.info(f"🏥 Queue health monitor started (interval: {check_interval}s)")

    while True:
        try:
            await asyncio.sleep(check_interval)

            for name, queue_logger in queue_loggers.items():
                stats = queue_logger.get_stats()
                current_size = stats["current_size"]

                if current_size >= warning_threshold:
                    logger.warning(
                        f"⚠️  Queue '{name}' is large: {current_size} items "
                        f"(threshold: {warning_threshold})"
                    )
                elif current_size > 0:
                    logger.debug(f"Queue '{name}' has {current_size} items")

        except Exception as e:
            logger.error(f"Error in queue health monitor: {e}")
