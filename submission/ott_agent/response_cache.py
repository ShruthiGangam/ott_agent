"""Cache only validated real model replies for byte-identical minimized inputs."""
import hashlib
import json
import time
from pathlib import Path
class ResponseCache:
    def __init__(self,path):
        self.path=Path(path) if path else None
        self.rows={}
        if self.path and self.path.exists() and self.path.stat().st_size<=2000000:
            try:
                value=json.loads(self.path.read_text(encoding='utf-8'))
                if isinstance(value,dict):
                    self.rows=value
            except (ValueError,OSError):
                pass
    @staticmethod
    def key(endpoint,model,prompt,payload):
        return hashlib.sha256(json.dumps({'endpoint':endpoint,'model':model,'prompt':prompt,'payload':payload},sort_keys=True).encode()).hexdigest()
    def get(self,key):
        row=self.rows.get(key)
        if isinstance(row,dict) and type(row.get('saved_at')) in (int,float) and 0<=time.time()-row['saved_at']<86400:
            return row
        return None
    def put(self,key,proposal,response_model,source=None):
        if self.path is None:
            return
        self.rows[key]={'proposal':proposal,'response_model':response_model,'saved_at':time.time(),'source':source or 'validated_live_api_response'}
        temporary=self.path.with_suffix(self.path.suffix+'.tmp')
        temporary.write_text(json.dumps(self.rows),encoding='utf-8')
        temporary.replace(self.path)
