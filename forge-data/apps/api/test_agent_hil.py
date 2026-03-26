import asyncio
import json
import logging
import sys
from unittest.mock import MagicMock, AsyncMock

# Mocking app modules
sys.modules['app.core.realtime'] = MagicMock()
sys.modules['app.services.workspace_service'] = MagicMock()
sys.modules['app.services.dataset_service'] = MagicMock()

from app.core.pipeline_engine import AgenticPipelineEngine, ToolTier
from app.core.code_generator import CodeGenerator
from app.models.user import User

async def test_agent_loop_and_approval():
    print("🚀 Starting Agentic Loop + Approval Test")
    
    # Setup mocks
    db = AsyncMock()
    kernel_mgr = AsyncMock()
    code_generator = AsyncMock()
    
    # Mock code generation for 'thinking'
    async def mock_explain(*args, **kwargs):
        yield "I am thinking about this step."
    code_generator.explain_output = mock_explain
    
    # Mock code generation for 'code_writer'
    async def mock_generate(*args, **kwargs):
        yield "import pandas as pd\n"
        yield "print('hello')"
    code_generator.generate_code = mock_generate
    
    engine = AgenticPipelineEngine(db=db, kernel_mgr=kernel_mgr, code_generator=code_generator)
    
    user = User(id=None) # Mocking user without DB
    workspace_id = "ws-456"
    goal = "Test delete dataset" 
    
    events = []
    async def stream_updates(event):
        events.append(event)
        print(f"📡 Event: {event['type']}")
        if event['type'] == 'approval_required':
            print(f"🔴 Approval required for: {event['tool']}")
            # Simulate human approval
            await engine._approval_queues[workspace_id].put(True)
            print("👤 Human approved action")

    # Mock _read_workspace_cells
    import app.core.pipeline_engine as pe
    pe._read_workspace_cells = AsyncMock(return_value="No cells.")
    
    print("🏃 Running pipeline...")
    try:
        # We need to mock the Pipeline and PipelineRun models too
        import app.models.pipeline as pm
        pm.Pipeline = MagicMock()
        pm.PipelineRun = MagicMock()
        
        await engine.run_pipeline(user, workspace_id, goal, stream_updates)
    except Exception as e:
        print(f"❌ Error during run: {e}")
        import traceback
        traceback.print_exc()

    print("\n✅ Test finished. Event sequence:")
    for e in events:
        print(f" - {e['type']}")

if __name__ == "__main__":
    asyncio.run(test_agent_loop_and_approval())
