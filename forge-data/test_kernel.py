import asyncio, json, uuid

async def test():
    import httpx, websockets
    # Create kernel
    async with httpx.AsyncClient() as client:
        r = await client.post('http://jupyter:8888/api/kernels', json={'name': 'python3'})
        print('Create kernel:', r.status_code)
        data = r.json()
        kernel_id = data['id']
        print('kernel_id:', kernel_id)

    # Wait for kernel to start
    await asyncio.sleep(1)

    # Execute code
    msg_id = str(uuid.uuid4())
    ws_url = f'ws://jupyter:8888/api/kernels/{kernel_id}/channels'
    execute_msg = {
        'header': {
            'msg_id': msg_id,
            'username': 'forge',
            'session': str(uuid.uuid4()),
            'msg_type': 'execute_request',
            'version': '5.3',
        },
        'parent_header': {},
        'metadata': {},
        'content': {
            'code': 'print("hello forge")\nresult = 2+2\nprint(f"2+2 = {result}")',
            'silent': False,
            'store_history': True,
            'user_expressions': {},
            'allow_stdin': False,
        },
    }

    async with websockets.connect(ws_url, open_timeout=10) as ws:
        await ws.send(json.dumps(execute_msg))
        print('Sent execute request, waiting for messages...')
        for _ in range(30):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                msg = json.loads(raw)
                mt = msg.get('msg_type', '')
                phdr = msg.get('parent_header', {})
                c = msg.get('content', {})
                print(f'  msg_type={mt} parent_msg_id={phdr.get("msg_id","")[:8]} content_keys={list(c.keys())}')
                if mt == 'stream':
                    print(f'    -> STREAM text: {repr(c.get("text",""))}')
                if mt == 'execute_reply':
                    print(f'    -> REPLY status: {c.get("status")}')
                    break
            except asyncio.TimeoutError:
                print('  timeout waiting for message')
                break

    # Cleanup
    async with httpx.AsyncClient() as client:
        await client.delete(f'http://jupyter:8888/api/kernels/{kernel_id}')
        print('Kernel deleted')

asyncio.run(test())
