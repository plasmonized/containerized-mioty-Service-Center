
import asyncio
import logging
import json
from queue_logger import setup_queue_logging, log_all_queue_stats

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_queue_logging():
    """Test the queue logging functionality"""
    logger.info("🧪 Testing Queue Logging Functionality")
    logger.info("=" * 50)
    
    # Create test queues
    queue_a = asyncio.Queue()
    queue_b = asyncio.Queue()
    
    # Setup logging
    queue_loggers = setup_queue_logging({
        'test_queue_a': queue_a,
        'test_queue_b': queue_b
    })
    
    # Test putting and getting items
    logger.info("📤 Testing queue operations...")
    
    # Put some test items
    await queue_a.put({"type": "test", "data": "message1"})
    await queue_a.put({"type": "test", "data": "message2"})
    await queue_b.put({"type": "config", "eui": "1234567890abcdef"})
    
    # Get items
    item1 = await queue_a.get()
    item2 = await queue_a.get()
    config_item = await queue_b.get()
    
    logger.info(f"Retrieved items: {item1}, {item2}, {config_item}")
    
    # Log final statistics
    log_all_queue_stats(queue_loggers)
    
    logger.info("✅ Queue logging test completed")

if __name__ == "__main__":
    asyncio.run(test_queue_logging())
