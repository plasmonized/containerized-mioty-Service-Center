
import asyncio
import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)

class QueueLogger:
    def __init__(self, queue_name: str, queue_instance: asyncio.Queue):
        self.queue_name = queue_name
        self.queue = queue_instance
        self.original_put = queue_instance.put
        self.original_get = queue_instance.get
        self.stats = {
            'put_count': 0,
            'get_count': 0,
            'current_size': 0,
            'max_size_seen': 0,
            'last_put_time': None,
            'last_get_time': None,
            'total_items_processed': 0
        }
        
        # Monkey patch the queue methods
        queue_instance.put = self._logged_put
        queue_instance.get = self._logged_get
        
        logger.info(f"🔍 Queue Logger initialized for '{queue_name}' (ID: {id(queue_instance)})")
    
    async def _logged_put(self, item: Any) -> None:
        """Logged version of queue.put()"""
        self.stats['put_count'] += 1
        self.stats['last_put_time'] = time.time()
        self.stats['current_size'] = self.queue.qsize() + 1
        self.stats['max_size_seen'] = max(self.stats['max_size_seen'], self.stats['current_size'])
        
        logger.info(f"📤 [{self.queue_name}] PUT #{self.stats['put_count']}")
        logger.info(f"   Queue ID: {id(self.queue)}")
        logger.info(f"   New size: {self.stats['current_size']}")
        logger.info(f"   Item type: {type(item).__name__}")
        if isinstance(item, dict):
            logger.info(f"   Item keys: {list(item.keys())}")
        
        await self.original_put(item)
    
    async def _logged_get(self) -> Any:
        """Logged version of queue.get()"""
        item = await self.original_get()
        
        self.stats['get_count'] += 1
        self.stats['last_get_time'] = time.time()
        self.stats['current_size'] = self.queue.qsize()
        self.stats['total_items_processed'] += 1
        
        logger.info(f"📥 [{self.queue_name}] GET #{self.stats['get_count']}")
        logger.info(f"   Queue ID: {id(self.queue)}")
        logger.info(f"   New size: {self.stats['current_size']}")
        logger.info(f"   Item type: {type(item).__name__}")
        if isinstance(item, dict):
            logger.info(f"   Item keys: {list(item.keys())}")
        
        return item
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        return {
            'queue_name': self.queue_name,
            'queue_id': id(self.queue),
            'current_size': self.queue.qsize(),
            **self.stats
        }
    
    def log_stats(self) -> None:
        """Log current queue statistics"""
        stats = self.get_stats()
        logger.info(f"📊 Queue Stats for '{self.queue_name}':")
        logger.info(f"   Queue ID: {stats['queue_id']}")
        logger.info(f"   Current size: {stats['current_size']}")
        logger.info(f"   Put operations: {stats['put_count']}")
        logger.info(f"   Get operations: {stats['get_count']}")
        logger.info(f"   Max size seen: {stats['max_size_seen']}")
        logger.info(f"   Total processed: {stats['total_items_processed']}")

def setup_queue_logging(queues: Dict[str, asyncio.Queue]) -> Dict[str, QueueLogger]:
    """Setup logging for multiple queues and return loggers"""
    loggers = {}
    
    logger.info("🔍 Setting up queue logging...")
    logger.info(f"   Number of queues to monitor: {len(queues)}")
    
    for name, queue in queues.items():
        loggers[name] = QueueLogger(name, queue)
        logger.info(f"   ✅ Queue '{name}' logging enabled (ID: {id(queue)})")
    
    return loggers

def log_all_queue_stats(queue_loggers: Dict[str, QueueLogger]) -> None:
    """Log statistics for all monitored queues"""
    logger.info("=" * 60)
    logger.info("📊 COMPREHENSIVE QUEUE STATISTICS")
    logger.info("=" * 60)
    
    for name, queue_logger in queue_loggers.items():
        queue_logger.log_stats()
        logger.info("-" * 40)
    
    # Check for queue ID conflicts/sharing
    queue_ids = {}
    for name, queue_logger in queue_loggers.items():
        queue_id = queue_logger.get_stats()['queue_id']
        if queue_id in queue_ids:
            logger.warning(f"⚠️  SHARED QUEUE DETECTED!")
            logger.warning(f"   Queue ID {queue_id} is used by both:")
            logger.warning(f"     - {queue_ids[queue_id]}")
            logger.warning(f"     - {name}")
        else:
            queue_ids[queue_id] = name
    
    logger.info("=" * 60)
