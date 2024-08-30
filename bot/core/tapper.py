import asyncio
import os
import random
import string
import sys
from time import time
from urllib.parse import parse_qs, unquote, quote

import aiohttp
import json
from aiocfscrape import CloudflareScraper
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered, FloodWait
from pyrogram.raw.functions.messages import RequestAppWebView
from pyrogram.raw import types
import requests
from .agents import generate_random_user_agent
from bot.config import settings

from bot.utils import logger
from bot.exceptions import InvalidSession
from .headers import headers
from .helper import format_duration

class Tapper:
    def __init__(self, tg_client: Client):

        self.session_name = tg_client.name
        self.tg_client = tg_client
        self.user_id = 0
        self.username = None
        self.first_name = None
        self.last_name = None
        self.fullname = None
        self.start_param = None
        self.peer = None
        self.first_run = None
        self.rf_token = ""
        self.session_ug_dict = self.load_user_agents() or []

        headers['User-Agent'] = self.check_user_agent()

    async def generate_random_user_agent(self):
        return generate_random_user_agent(device_type='android', browser_type='chrome')

    def info(self, message):
        from bot.utils import info
        info(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def debug(self, message):
        from bot.utils import debug
        debug(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def warning(self, message):
        from bot.utils import warning
        warning(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def error(self, message):
        from bot.utils import error
        error(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def critical(self, message):
        from bot.utils import critical
        critical(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def success(self, message):
        from bot.utils import success
        success(f"<light-yellow>{self.session_name}</light-yellow> | {message}")

    def save_user_agent(self):
        user_agents_file_name = "user_agents.json"

        if not any(session['session_name'] == self.session_name for session in self.session_ug_dict):
            user_agent_str = generate_random_user_agent()

            self.session_ug_dict.append({
                'session_name': self.session_name,
                'user_agent': user_agent_str})

            with open(user_agents_file_name, 'w') as user_agents:
                json.dump(self.session_ug_dict, user_agents, indent=4)

            logger.success(f"<light-yellow>{self.session_name}</light-yellow> | User agent saved successfully")

            return user_agent_str

    def load_user_agents(self):
        user_agents_file_name = "user_agents.json"

        try:
            with open(user_agents_file_name, 'r') as user_agents:
                session_data = json.load(user_agents)
                if isinstance(session_data, list):
                    return session_data

        except FileNotFoundError:
            logger.warning("User agents file not found, creating...")

        except json.JSONDecodeError:
            logger.warning("User agents file is empty or corrupted.")

        return []

    def check_user_agent(self):
        load = next(
            (session['user_agent'] for session in self.session_ug_dict if session['session_name'] == self.session_name),
            None)

        if load is None:
            return self.save_user_agent()

        return load

    async def get_tg_web_data(self, proxy: str | None) -> str:
        if proxy:
            proxy = Proxy.from_str(proxy)
            proxy_dict = dict(
                scheme=proxy.protocol,
                hostname=proxy.host,
                port=proxy.port,
                username=proxy.login,
                password=proxy.password
            )
        else:
            proxy_dict = None

        self.tg_client.proxy = proxy_dict

        try:
            with_tg = True

            if not self.tg_client.is_connected:
                with_tg = False
                try:
                    await self.tg_client.connect()
                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    raise InvalidSession(self.session_name)

            while True:
                try:
                    if self.peer is None:
                        self.peer = await self.tg_client.resolve_peer('pokequest_bot')
                    break
                except FloodWait as fl:
                    fls = fl.value

                    logger.warning(f"<light-yellow>{self.session_name}</light-yellow> | FloodWait {fl}")
                    logger.info(f"<light-yellow>{self.session_name}</light-yellow> | Sleep {fls}s")

                    await asyncio.sleep(fls + 3)

            if settings.REF_ID == '':
                self.start_param = '1BrRovf5vB'
            else:
                self.start_param = settings.REF_ID

            InputBotApp = types.InputBotAppShortName(bot_id=self.peer, short_name="app")

            web_view = await self.tg_client.invoke(RequestAppWebView(
                peer=self.peer,
                app=InputBotApp,
                platform='android',
                write_allowed=True,
                start_param=self.start_param
            ))

            auth_url = web_view.url
            #print(auth_url)
            tg_web_data = unquote(
                string=auth_url.split('tgWebAppData=', maxsplit=1)[1].split('&tgWebAppVersion', maxsplit=1)[0])

            try:
                if self.user_id == 0:
                    information = await self.tg_client.get_me()
                    self.user_id = information.id
                    self.first_name = information.first_name or ''
                    self.last_name = information.last_name or ''
                    self.username = information.username or ''
            except Exception as e:
                print(e)

            if with_tg is False:
                await self.tg_client.disconnect()

            return tg_web_data

        except InvalidSession as error:
            raise error

        except Exception as error:
            logger.error(
                f"<light-yellow>{self.session_name}</light-yellow> | Unknown error during Authorization: {error}")
            await asyncio.sleep(delay=3)

    async def login(self, http_client: aiohttp.ClientSession, init_data):
        try:
            parsed_query = parse_qs(init_data)
            final_json = {}

            for key, values in parsed_query.items():
                if key == "user" and values:
                    user_json_str = values[0]
                    final_json[key] = json.loads(unquote(user_json_str))
                else:
                    final_json[key] = values[0] if values else None
            data = json.dumps(final_json)
            resp = await http_client.post(f'https://api.pokey.quest/auth/login',data=data,
                                          ssl=False)
            
            resp.raise_for_status()
            resp_json = await resp.json()
            token = resp_json["data"]["token"]
            return token

        except Exception as error:
            logger.error(f"<light-yellow>{self.session_name}</light-yellow> | Login error {error}")

    async def user_info(self, http_client: aiohttp.ClientSession):
        try:
            resp = await http_client.post(f'https://api.pokey.quest/tap/sync',
                                          ssl=False)
            resp.raise_for_status()
            resp_json = await resp.json()

            return resp_json
        except Exception as error:
            logger.error(f"<light-yellow>{self.session_name}</light-yellow> | Claim task error {error}")

    async def get_tasks(self, http_client: aiohttp.ClientSession):
        try:
            resp = await http_client.get('https://api.pokey.quest/mission/list', ssl=False)
            resp_json = await resp.json()
            tasks = resp_json["data"]
        
           
            if isinstance(tasks, list):
                return tasks
            else:
                logger.error(f"{self.session_name} | Unexpected response format in get_tasks: {tasks}")
                return []
        except Exception as error:
            logger.error(f"<light-yellow>{self.session_name}</light-yellow> | Get tasks error {error}")

    async def get_partner_tasks(self, http_client: aiohttp.ClientSession):
        try:
            resp = await http_client.get('https://api.pokey.quest/partner-mission/list', ssl=False)
            resp_json = await resp.json()
            tasks = resp_json["data"]["data"]
            missions = []
            for task in tasks:
                missions.extend(task.get("partner_missions"))
           
            if isinstance(missions, list):
                return missions
            else:
                logger.error(f"{self.session_name} | Unexpected response format in get_tasks: {tasks}")
                return []
        except Exception as error:
            logger.error(f"<light-yellow>{self.session_name}</light-yellow> | Get tasks error {error}")

    async def do_partner_task(self, http_client: aiohttp.ClientSession,mission_id):
        try:
            data = {"partner_mission_id": mission_id}
            resp = await http_client.post("https://api.pokey.quest/user-partner-mission/claim", json = data, ssl=False)
            response_data = await resp.json()

            return response_data
        except Exception as e:
            self.error(f"Error occurred during start game: {e}")

    async def do_task(self, http_client: aiohttp.ClientSession,mission_id):
        try:
            data = {"mission_id": mission_id}
            resp = await http_client.post("https://api.pokey.quest/mission/claim", json = data, ssl=False)
            response_data = await resp.json()

            return response_data
        except Exception as e:
            self.error(f"Error occurred during start game: {e}")

    async def get_friend(self, http_client: aiohttp.ClientSession):
        try:
            resp = await http_client.get("https://api.pokey.quest/referral/list",
                                          ssl=False)
            resp.raise_for_status()
            resp_json = await resp.json()
            
            return resp_json["data"]["data"]
        except Exception as error:
            logger.error(f"<light-yellow>{self.session_name}</light-yellow> | Get friend error {error}")

    async def claim_friend(self, http_client: aiohttp.ClientSession,friend_id):
        try:
            data = {"friend_id": friend_id}
            resp = await http_client.post("https://api.pokey.quest/referral/claim-friend",json=data, ssl=False)
            resp.raise_for_status()
            
            resp_json = await resp.json()
            return resp_json["data"]["success"]
        
        except Exception as e:
            self.error(f"Error occurred during claim: {e}")

    async def farm(self, http_client: aiohttp.ClientSession):
        try:
            resp = await http_client.post("https://api.pokey.quest/pokedex/farm", ssl=False)
            
            resp_json = await resp.json()

            return resp_json
        except Exception as e:
            self.error(f"Error occurred during balance: {e}")

    async def upgrade(self, http_client: aiohttp.ClientSession):
        try:
            resp = await http_client.post("https://api.pokey.quest/poke/upgrade",
                                          ssl=False)
            # resp.raise_for_status()
            resp_json = await resp.json()
            return resp_json
        except Exception as e:
            self.error(f"Error occurred during upgrade: {e}")

    async def tap(self, http_client: aiohttp.ClientSession, tap_count):
        data = {"count": tap_count}
        try:
            resp = await http_client.post("https://api.pokey.quest/tap/tap", json=data, ssl=False)

            # resp.raise_for_status()
            resp_json = await resp.json()

            return resp_json
        except Exception as e:
            self.error(f"Error occurred during taping: {e}")
    
    async def list_card(self, http_client: aiohttp.ClientSession):
        try:
            resp = await http_client.get("https://api.pokey.quest/pokedex/list",
                                            ssl=False)
            resp.raise_for_status()
            resp_json = await resp.json()
            
            return resp_json["data"]["data"]
        except Exception as error:
            logger.error(f"<light-yellow>{self.session_name}</light-yellow> | Get card error {error}")

    async def upgrade_card(self, http_client: aiohttp.ClientSession,card_id):
        try:
            resp = await http_client.post("https://api.pokey.quest/pokedex/upgrade",json= {"card_id": card_id},
                                            ssl=False)
            # resp.raise_for_status()
            resp_json = await resp.json()
            
            return resp_json["error_code"] == "OK"
        except Exception as error:
            logger.error(f"<light-yellow>{self.session_name}</light-yellow> | Get card error {error}")

    async def check_proxy(self, http_client: aiohttp.ClientSession, proxy: Proxy) -> None:
        try:
            response = await http_client.get(url='https://httpbin.org/ip', timeout=aiohttp.ClientTimeout(5))
            ip = (await response.json()).get('origin')
            logger.info(f"<light-yellow>{self.session_name}</light-yellow> | Proxy IP: {ip}")
        except Exception as error:
            logger.error(f"<light-yellow>{self.session_name}</light-yellow> | Proxy: {proxy} | Error: {error}")

    async def run(self, proxy: str | None) -> None:

        access_token = None
        
        proxy_conn = ProxyConnector().from_url(proxy) if proxy else None

        http_client = CloudflareScraper(headers=headers, connector=proxy_conn)

        if proxy:
            await self.check_proxy(http_client=http_client, proxy=proxy)

        #print(init_data)

        while True:
            try:
                init_data = await self.get_tg_web_data(proxy=proxy)
                access_token = await self.login(http_client=http_client, init_data=init_data)

                if access_token:
                    http_client.headers["Authorization"] = f"Bearer {access_token}"
    
                    # Get user info
                    user_info = await self.user_info(http_client=http_client)

                    level = user_info["data"]["level"]
                    available_taps = user_info["data"]["available_taps"]
                    self.info(f"Available taps: <green>{available_taps}</green>")
                    balances = user_info["data"]["balance_coins"]
                    inf = ""
                    for balance in balances:
                        coin_type = balance["currency_symbol"]
                        coin_balance = balance["balance"]
                        inf += f"<cyan>{coin_type}</cyan> balance: <green>{coin_balance:,}</green> "
                    self.info(inf)

                    # Do task
                    if settings.AUTO_TASK:
                        tasks = await self.get_tasks(http_client=http_client)
                        for task in tasks:
                            task_id = task["id"]
                            task_name = task["title"]

                            do_task = await self.do_task(http_client=http_client,mission_id=task_id)

                            status = do_task["data"]["success"]
                            if status:
                                self.success(f"{task_name}: Succeeded!")

                            else:
                                self.error(f"{task_name}: Cannot process or Completed")
                            await asyncio.sleep(delay=2)
                    
                    # Do partner task
                    missions = await self.get_partner_tasks(http_client=http_client)
                    if missions: 
                        for mission in missions:
                            res = await self.do_partner_task(http_client=http_client,mission_id=mission["pm_id"])
                            await asyncio.sleep(random.randint(2,10))
                            if res.get("error_code","") == "OK":
                                self.success(f"{mission.get('title')}: Succeeded!")
                            else:
                                self.info(f"{mission.get('title')}:Cannot process or Completed")
                                
                    
                    # Claim friend
                    friends = await self.get_friend(http_client=http_client)
                
                    for friend in friends:
                        friend_id = friend["id"]
                        status = await self.claim_friend(
                            http_client=http_client, friend_id=friend_id
                        )
                        if status:
                            self.success(f"Friend {friend_id}: Success")
                        else:
                            self.info(f"Friend {friend_id}: Claimed")
                        await asyncio.sleep(delay=2)
                    
                    # Reward from collection
                    farm = await self.farm(http_client=http_client)
                    try:
                        gold_reward = farm["data"]["gold_reward"]
                        self.success(f"Gold reward:{gold_reward}")
                    except:
                        self.error(
                            f"Get reward from collection:Not time to claim"
                        )

                    # Upgrade
                    if settings.AUTO_UPGRAGE:
                        
                        upgrade = await self.upgrade(http_client=http_client)
                        if upgrade:
                            status = upgrade["error_code"]
                            if status == "OK":
                                level = upgrade["data"]["level"]
                                max_taps = upgrade["data"]["max_taps"]
                                self.success(f"New level: <cyan>{level}</cyan> - Max taps: <cyan>{max_taps}</cyan>")
                            elif status == "INSUFFICIENT_BALANCE":
                                self.info(f"Auto Upgrade: Not enough coin")
                            else:
                                self.error(f"Auto Upgrade: Unknown")
                    #upgrade card
                    cards = await self.list_card(http_client=http_client)
                    upgrade_cards = [ 
                            card for card in cards 
                            if  card["amount"] >= card["amount_card"] 
                                and card["level"] <= settings.UPGRADE_LEVEL 
                                and card["amount_gold"] <= balances[0]["balance"]
                                and card["amount_friend"] <= balances[1]["balance"]
                            ]
                    for upgrade_card in upgrade_cards:
                        status = await self.upgrade_card(http_client=http_client,card_id = upgrade_card["id"]) 
                        card_name = upgrade_card["name"]
                        if status: 
                            self.success(f"upgrade card <cyan>{card_name}</cyan> succeeded!")
                        else: 
                            self.success(f"upgrade card <cyan>{card_name}</cyan> failed!")
                        await asyncio.sleep(random.randint(2,8)) 
                    
                    while True:
                        inf = ""
                        taps = random.randint(settings.TAP_COUNT[0],settings.TAP_COUNT[1])
                        data = await self.tap(http_client=http_client, tap_count=taps)
                        if data:
                            level = data["data"]["level"]
                            available_taps = data["data"]["available_taps"]
                            self.success(f"Level: <cyan>{level}</cyan> - Available taps: <cyan>{available_taps}</cyan>")
                            balances = data["data"]["balance_coins"]
                            for balance in balances:
                                coin_type = balance["currency_symbol"]
                                coin_balance = balance["balance"]
                                inf += f"<cyan>{coin_type}</cyan> balance: <green>{coin_balance:,}</green> "
                            
                            self.info(inf)
                            await asyncio.sleep(random.randint(2,8))
                            if available_taps == 0:
                                break
                else:
                    await asyncio.sleep(random.randint(10,20))

            except InvalidSession as error:
                raise error

            except Exception as error:
                logger.error(f"<light-yellow>{self.session_name}</light-yellow> | Unknown error: {error}")
                await asyncio.sleep(delay=3)
            else:
                wait_time = random.randint(settings.SLEEP[0],settings.SLEEP[1])
                self.info(f"Wait for {int(wait_time)} minutes!")
                await asyncio.sleep(wait_time*60)


async def run_tapper(tg_client: Client, proxy: str | None):
    try:
        await Tapper(tg_client=tg_client).run(proxy=proxy)
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
