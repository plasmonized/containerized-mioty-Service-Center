
import asyncio
import shutil
import os
import logging
import time
from datetime import datetime

# Configure logging for test
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def run_test_suite():
    """Run the BSSCI test suite with test configuration"""
    
    print("🧪 BSSCI COMPREHENSIVE TEST SUITE")
    print("=" * 80)
    print(f"🕐 Starting at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Backup original config
    print("💾 Backing up original configuration...")
    try:
        shutil.copy("bssci_config.py", "bssci_config_backup.py")
        print("✅ Configuration backed up")
    except Exception as e:
        print(f"⚠️  Warning: Could not backup config: {e}")
    
    # Switch to test configuration
    print("🔧 Switching to test configuration...")
    try:
        shutil.copy("bssci_config_test.py", "bssci_config.py")
        print("✅ Test configuration activated")
        print("📡 MQTT topic changed to: test/")
    except Exception as e:
        print(f"❌ Error switching to test config: {e}")
        return
    
    try:
        # Start BSSCI server in background
        print("\n🚀 Starting BSSCI server...")
        
        # Import after config switch
        import main
        
        # Start server task
        server_task = asyncio.create_task(main.main())
        
        # Wait for server to start
        print("⏳ Waiting for server to initialize...")
        await asyncio.sleep(5)
        
        # Run the comprehensive test
        print("\n🧪 Running comprehensive test...")
        from test_bssci_comprehensive import run_comprehensive_bssci_test
        await run_comprehensive_bssci_test()
        
        # Cancel server
        print("\n🛑 Stopping BSSCI server...")
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        
    except Exception as e:
        print(f"❌ Test execution error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Restore original configuration
        print("\n🔄 Restoring original configuration...")
        try:
            if os.path.exists("bssci_config_backup.py"):
                shutil.copy("bssci_config_backup.py", "bssci_config.py")
                os.remove("bssci_config_backup.py")
                print("✅ Original configuration restored")
            else:
                print("⚠️  No backup found, manual restoration may be needed")
        except Exception as e:
            print(f"❌ Error restoring config: {e}")
        
        print(f"\n🎯 TEST SUITE COMPLETE")
        print(f"🕐 Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    # Set up event loop policy for Windows compatibility
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass  # Not on Windows
    
    asyncio.run(run_test_suite())
