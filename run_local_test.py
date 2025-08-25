
#!/usr/bin/env python3

import asyncio
import shutil
import os
import sys
from datetime import datetime

async def run_local_test():
    """Run BSSCI test with local non-SSL configuration"""
    
    print("🧪 BSSCI LOCAL TEST RUNNER")
    print("=" * 60)
    print(f"🕐 Starting at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Backup original config if it exists
    config_backup = None
    if os.path.exists("bssci_config.py"):
        print("💾 Backing up original bssci_config.py...")
        config_backup = "bssci_config_backup.py"
        shutil.copy("bssci_config.py", config_backup)
        print("✅ Backup created")
    
    try:
        # Switch to local test config
        print("🔧 Switching to local test configuration (no SSL)...")
        if os.path.exists("bssci_config_local_test.py"):
            shutil.copy("bssci_config_local_test.py", "bssci_config.py")
            print("✅ Local test configuration activated")
            print("   - SSL/TLS: DISABLED")
            print("   - MQTT Topic: test/")
            print("   - Listen: 0.0.0.0:16017")
        else:
            print("❌ Local test configuration not found!")
            return
        
        # Import main after config switch
        print("\n🚀 Starting BSSCI server...")
        import main
        
        # Start server in background
        server_task = asyncio.create_task(main.main())
        
        # Wait for server to start
        print("⏳ Waiting for server to initialize...")
        await asyncio.sleep(3)
        
        # Run configuration check
        print("\n🔍 Running configuration check...")
        from check_bssci_config import main as check_main
        await check_main()
        
        # Run comprehensive test
        print("\n🧪 Running comprehensive test...")
        from test_bssci_local_complete import run_comprehensive_local_test
        await run_comprehensive_local_test()
        
        # Keep server running for a moment
        print("\n⏸️  Keeping server running for 5 seconds...")
        await asyncio.sleep(5)
        
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cancel server
        try:
            server_task.cancel()
            await server_task
        except:
            pass
        
        # Restore original config
        if config_backup and os.path.exists(config_backup):
            print("\n🔄 Restoring original configuration...")
            shutil.copy(config_backup, "bssci_config.py")
            os.remove(config_backup)
            print("✅ Original configuration restored")
        
        print(f"\n🎯 LOCAL TEST COMPLETE")
        print(f"🕐 Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        pass
    
    asyncio.run(run_local_test())
