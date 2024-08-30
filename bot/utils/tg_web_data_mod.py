import urllib.parse
import json


class tg_web_data_mod:
    def __init__(self,query:str) -> None:
        self.query = query
        
    def name(self):
        parsed_query = urllib.parse.parse_qs(self.query)
        user_data = json.loads(parsed_query['user'][0])
        return f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}"
    
    def tg_web_data(self):
        return self.query 