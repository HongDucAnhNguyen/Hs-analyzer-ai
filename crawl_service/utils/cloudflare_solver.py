"""Cloudflare bypass utilities using Zendriver

Provides CloudflareSolver class that handles Cloudflare challenges
using CF-Clearance-Scraper pattern.
"""

from __future__ import annotations

import asyncio
import logging
import random
from enum import Enum
from typing import Any, Iterable, List, Optional

import latest_user_agents
import user_agents
import zendriver
from selenium_authenticated_proxy import SeleniumAuthenticatedProxy
from zendriver import cdp
from zendriver.cdp.emulation import UserAgentBrandVersion, UserAgentMetadata
from zendriver.cdp.network import T_JSON_DICT, Cookie
from zendriver.core.element import Element

logger = logging.getLogger(__name__)


def get_chrome_user_agent() -> str:
    """Get a random up-to-date Chrome user agent string."""
    chrome_user_agents = [
        ua for ua in latest_user_agents.get_latest_user_agents()
        if "Chrome" in ua and "Edg" not in ua
    ]
    return random.choice(chrome_user_agents)


class ChallengePlatform(Enum):
    """Cloudflare challenge platform types."""
    JAVASCRIPT = "non-interactive"
    MANAGED = "managed"
    INTERACTIVE = "interactive"


class CloudflareSolver:
    """Solves Cloudflare challenges with Zendriver."""

    def __init__(
        self,
        *,
        user_agent: Optional[str] = None,
        timeout: float = 60,
        headless: bool = True,
        proxy: Optional[str] = None,
    ) -> None:
        config = zendriver.Config(headless=headless)
        
        if user_agent:
            config.add_argument(f"--user-agent={user_agent}")
        
        config.add_argument("--disable-quic")
        
        if proxy:
            SeleniumAuthenticatedProxy(proxy).enrich_chrome_options(config)
        
        self.driver = zendriver.Browser(config)
        self._timeout = timeout
        self._user_agent = user_agent

    async def __aenter__(self) -> CloudflareSolver:
        await self.driver.start()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.driver.stop()

    @staticmethod
    def _format_cookies(cookies: Iterable[Cookie]) -> List[T_JSON_DICT]:
        return [cookie.to_json() for cookie in cookies]

    @staticmethod
    def extract_clearance_cookie(cookies: Iterable[T_JSON_DICT]) -> Optional[T_JSON_DICT]:
        for cookie in cookies:
            if cookie["name"] == "cf_clearance":
                return cookie
        return None

    async def get_user_agent(self) -> str:
        return await self.driver.main_tab.evaluate("navigator.userAgent")

    async def get_cookies(self) -> List[T_JSON_DICT]:
        return self._format_cookies(await self.driver.cookies.get_all())

    async def get_current_url(self) -> str:
        return await self.driver.main_tab.evaluate("window.location.href")

    async def set_user_agent_metadata(self, user_agent: str) -> None:
        device = user_agents.parse(user_agent)
        metadata = UserAgentMetadata(
            architecture="x86",
            bitness="64",
            brands=[
                UserAgentBrandVersion(brand="Not)A;Brand", version="8"),
                UserAgentBrandVersion(brand="Chromium", version=str(device.browser.version[0])),
                UserAgentBrandVersion(brand="Google Chrome", version=str(device.browser.version[0])),
            ],
            full_version_list=[
                UserAgentBrandVersion(brand="Not)A;Brand", version="8"),
                UserAgentBrandVersion(brand="Chromium", version=str(device.browser.version[0])),
                UserAgentBrandVersion(brand="Google Chrome", version=str(device.browser.version[0])),
            ],
            mobile=device.is_mobile,
            model=device.device.model or "",
            platform=device.os.family,
            platform_version=device.os.version_string,
            full_version=device.browser.version_string,
            wow64=False,
        )
        self.driver.main_tab.feed_cdp(
            cdp.network.set_user_agent_override(user_agent, user_agent_metadata=metadata)
        )

    async def detect_challenge(self) -> Optional[ChallengePlatform]:
        html = await self.driver.main_tab.get_content()
        for platform in ChallengePlatform:
            if f"cType: '{platform.value}'" in html:
                return platform
        return None

    async def solve_challenge(self) -> None:
        from datetime import datetime
        start = datetime.now()
        
        while (
            self.extract_clearance_cookie(await self.get_cookies()) is None
            and await self.detect_challenge() is not None
            and (datetime.now() - start).seconds < self._timeout
        ):
            widget_input = await self.driver.main_tab.find("input")
            
            if widget_input.parent is None or not widget_input.parent.shadow_roots:
                await asyncio.sleep(0.25)
                continue
            
            challenge = Element(
                widget_input.parent.shadow_roots[0],
                self.driver.main_tab,
                widget_input.parent.tree,
            ).children[0]
            
            if isinstance(challenge, Element) and "display: none;" not in challenge.attrs.get("style", ""):
                await asyncio.sleep(1)
                try:
                    await challenge.get_position()
                    await challenge.mouse_click()
                except Exception:
                    continue

    async def navigate_and_bypass(self, url: str, max_retries: int = 3) -> str:
        """Navigate to URL and bypass Cloudflare. Returns page HTML."""
        logger.info(f"[Zendriver] Navigating to: {url}")
        
        try:
            await self.driver.get(url)
        except asyncio.TimeoutError as e:
            logger.error(f"[Zendriver] Timeout: {e}")
            raise
        
        await asyncio.sleep(3)
        
        for attempt in range(max_retries):
            html = await self.driver.main_tab.get_content()
            is_challenge = "Just a moment" in html or "Verifying you are human" in html
            
            if self.extract_clearance_cookie(await self.get_cookies()) and not is_challenge:
                logger.info("[Zendriver] Bypassed Cloudflare")
                return html
            
            if is_challenge:
                logger.info(f"[Zendriver] Challenge detected, attempt {attempt + 1}/{max_retries}")
                await self.set_user_agent_metadata(await self.get_user_agent())
                
                if platform := await self.detect_challenge():
                    logger.info(f"[Zendriver] Solving [{platform.value}]...")
                    try:
                        await self.solve_challenge()
                    except Exception as e:
                        logger.warning(f"[Zendriver] Solve error: {e}")
                
                await asyncio.sleep(5)
            else:
                return html
        
        html = await self.driver.main_tab.get_content()
        if "Just a moment" in html:
            logger.warning("[Zendriver] Still blocked after all attempts")
        return html

