"""Bound inventory request bodies, including chunked requests, before parsing."""
import json


class InventoryRequestLimits:
    def __init__(self, app):
        self.app=app

    async def __call__(self, scope, receive, send):
        if scope['type']!='http' or not scope['path'].startswith('/api/v1/inventory/') or scope['method'] not in {'POST','PUT','PATCH'}:
            return await self.app(scope,receive,send)
        limit=5*1024*1024 if '/count-sessions/' in scope['path'] and scope['path'].endswith('/evidence') else 256000
        parts=[];size=0
        while True:
            message=await receive()
            if message['type']=='http.disconnect':
                return
            body=message.get('body',b'');size+=len(body)
            if size>limit:
                payload=json.dumps({'detail':'Inventory request exceeds the upload or JSON size limit'}).encode()
                await send({'type':'http.response.start','status':413,'headers':[(b'content-type',b'application/json'),(b'content-length',str(len(payload)).encode())]})
                await send({'type':'http.response.body','body':payload});return
            parts.append(body)
            if not message.get('more_body',False):break
        delivered=False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered=True
                return {'type':'http.request','body':b''.join(parts),'more_body':False}
            return await receive()
        await self.app(scope,bounded_receive,send)
