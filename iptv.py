#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import json
import time
import socket
import asyncio
import ipaddress
import subprocess
import urllib.parse
import random
import traceback
from collections.abc import Iterable
from urllib.parse import urlparse, quote

import requests
from bs4 import BeautifulSoup

# ==================== 全局配置 ====================
CONFIG = {
    # 文件配置
    'final_file': 'result.txt',
    
    # 测速权重配置
    'response_time_weight': 0.6,
    'resolution_weight': 0.4,
    
    # 频道配置
    'max_urls_per_channel': 8,
    
    # 性能配置
    'max_concurrent_tasks': 10,
    
    # 测速配置
    'open_sort': True,
    'ffmpeg_time': 10,
    
    # 网络配置
    'ipv_type': "ipv4",
    
    # 过滤配置
    'domain_blacklist': [],
    'url_keywords_blacklist': [],
    'search_ignore_key': ["高清", "4K", "HD", "HDR", "杜比", "Dolby"],
    
    # 搜索配置
    'search_regions': ["全国"],
    'search_page_num': 8,
    
    # 爬取模式配置 (1-tonkiang组播源, 2-crawl_urls, 3-全部)
    'crawl_type': "3",
    
    # 订阅源配置 (用于提取RTP路径)
    'search_dict': {
        "上海": "https://raw.githubusercontent.com/xisohi/IPTV-Multicast-source/main/shanghai/telecom.txt",
        "北京": "https://raw.githubusercontent.com/xisohi/IPTV-Multicast-source/main/beijing/unicom.txt",
        "广东": "https://raw.githubusercontent.com/xisohi/IPTV-Multicast-source/main/guangdong/telecom.txt"
    },
    
    # 其他直播源URL
    'crawl_urls': [
        "https://raw.githubusercontent.com/PizazzGY/TVBox/main/live.txt",
        "https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",
        "https://raw.githubusercontent.com/ssili126/tv/main/itvlist.txt"
    ],
    
    # 模板频道列表配置
    'channel_list': {
        "央视频道": [
            "CCTV-1", "CCTV-2", "CCTV-3", "CCTV-4", "CCTV-5", "CCTV-5+", "CCTV-6", "CCTV-7", 
            "CCTV-8", "CCTV-9", "CCTV-10", "CCTV-11", "CCTV-12", "CCTV-13", "CCTV-14", "CCTV-15",
            "CCTV-16", "CCTV-17", "CCTV-新闻", "CCTV-少儿", "CCTV-音乐", "CCTV-戏曲", "CCTV-社会与法"
        ],
        "卫视频道": [
            "北京卫视", "天津卫视", "河北卫视", "山西卫视", "内蒙古卫视", "辽宁卫视", "吉林卫视", 
            "黑龙江卫视", "东方卫视", "江苏卫视", "浙江卫视", "安徽卫视", "福建卫视", "江西卫视", 
            "山东卫视", "河南卫视", "湖北卫视", "湖南卫视", "广东卫视", "广西卫视", "海南卫视", 
            "重庆卫视", "四川卫视", "贵州卫视", "云南卫视", "陕西卫视", "甘肃卫视", "宁夏卫视"
        ],
        "高清频道": [
            "CCTV-1高清", "CCTV-2高清", "CCTV-3高清", "CCTV-4高清", "CCTV-5高清", "CCTV-6高清",
            "CCTV-7高清", "CCTV-8高清", "CCTV-9高清", "CCTV-10高清", "CCTV-11高清", "CCTV-12高清",
            "CCTV-13高清", "CCTV-14高清", "CCTV-15高清", "北京卫视高清", "湖南卫视高清", 
            "浙江卫视高清", "江苏卫视高清", "东方卫视高清", "广东卫视高清", "深圳卫视高清"
        ],
        "4K频道": [
            "CCTV-4K", "北京卫视4K", "上海纪实4K", "湖南卫视4K", "浙江卫视4K", "江苏卫视4K",
            "东方卫视4K", "广东卫视4K", "深圳卫视4K", "CCTV-16-4K"
        ],
        "地方频道": [
            "北京文艺", "北京科教", "北京影视", "北京财经", "北京生活", "北京青年", "北京新闻",
            "上海新闻综合", "上海东方影视", "上海娱乐", "上海体育", "上海纪实", "上海第一财经",
            "广东珠江", "广东体育", "广东公共", "广东新闻", "深圳都市", "深圳公共", "深圳电视剧",
            "重庆新闻", "重庆影视", "重庆文艺", "重庆社会与法", "浙江钱江", "浙江教育科技",
            "江苏城市", "江苏影视", "江苏公共新闻", "湖南经视", "湖南都市", "湖南娱乐"
        ],
        "体育频道": [
            "CCTV-5", "CCTV-5+", "广东体育", "北京体育", "上海体育", "江苏体育", "浙江体育",
            "山东体育", "辽宁体育", "湖北体育", "湖南体育", "四川体育", "天津体育", "重庆体育",
            "劲爆体育", "足球频道", "高尔夫网球"
        ],
        "影视娱乐": [
            "CCTV-6", "CCTV-8", "东方影视", "湖南电影", "广东电影", "江苏影视", "浙江影视",
            "山东影视", "四川影视", "重庆影视", "湖北影视", "天津影视", "北京影视", "上海影视"
        ],
        "少儿卡通": [
            "CCTV-14", "卡酷少儿", "炫动卡通", "金鹰卡通", "优漫卡通", "嘉佳卡通", "北京少儿",
            "上海哈哈炫动", "广东少儿", "江苏优漫", "浙江少儿", "山东少儿", "湖南金鹰"
        ],
        "新闻财经": [
            "CCTV-13", "CCTV-2", "凤凰资讯", "深圳财经", "第一财经", "广东新闻", "北京新闻",
            "上海新闻", "江苏新闻", "浙江新闻", "山东新闻", "四川新闻", "湖北综合", "湖南经视"
        ]
    }
}

# ==================== 配置类 ====================
class DynamicConfig:
    """动态配置类"""
    def __init__(self):
        # 直接从全局配置加载
        for key, value in CONFIG.items():
            setattr(self, key, value)
        
        # 验证配置有效性
        self._validate_config()
    
    def _validate_config(self):
        """验证配置有效性"""
        # 验证权重配置
        if not (0 <= self.response_time_weight <= 1 and 0 <= self.resolution_weight <= 1):
            print("⚠ 权重配置无效，使用默认值")
            self.response_time_weight = 0.5
            self.resolution_weight = 0.5
        
        # 验证并发数
        if self.max_concurrent_tasks <= 0:
            print("⚠ 并发任务数无效，使用默认值")
            self.max_concurrent_tasks = 10
        
        # 验证URL数量限制
        if self.max_urls_per_channel <= 0:
            print("⚠ URL数量限制无效，使用默认值")
            self.max_urls_per_channel = 8
        
        # 验证频道列表
        if not self.channel_list:
            print("⚠ 频道列表为空，使用默认频道")
            self.channel_list = {
                "默认频道": ["CCTV-1", "CCTV-2", "湖南卫视", "浙江卫视"]
            }

# ==================== 核心功能类 ====================
class IPTVProcessor:
    """IPTV直播源处理器"""
    
    def __init__(self, config):
        self.config = config
        self.previous_result_dict = {}
    
    def getChannelItems(self):
        """从配置获取频道项 - 严格按照模板"""
        channels = {}
        
        # 严格按照配置的channel_list获取频道
        if hasattr(self.config, 'channel_list') and self.config.channel_list:
            for category, channel_names in self.config.channel_list.items():
                channels[category] = {}
                for channel_name in channel_names:
                    channels[category][channel_name] = []  # 空的URL列表
        
        return channels
    
    def updateChannelUrlsTxt(self, cate, channelUrls):
        """更新分类和频道URL到最终文件 - 严格按照模板顺序"""
        try:
            with open("result_new.txt", "a", encoding="utf-8") as f:
                f.write(f"{cate},#genre#\n")
                for name, urls in channelUrls.items():
                    for url in urls:
                        if url and url.strip():
                            f.write(f"{name},{url}\n")
                f.write("\n")
        except Exception as e:
            print(f"❌ 更新频道URL文件错误: {e}")
    
    def updateFile(self, final_file, old_file):
        """更新文件"""
        try:
            if os.path.exists(old_file):
                if os.path.exists(final_file):
                    os.remove(final_file)
                    time.sleep(1)
                os.replace(old_file, final_file)
                print(f"✓ 文件更新完成: {final_file}")
            else:
                print(f"⚠ 临时文件不存在: {old_file}")
        except Exception as e:
            print(f"❌ 文件更新错误: {e}")
    
    async def check_stream_speed(self, url_info):
        """检查流媒体速度"""
        try:
            url = url_info[0]
            if not url or not url.strip():
                return float("-inf")
            
            video_info = await self.ffmpeg_url(url, self.config.ffmpeg_time)
            if video_info is None:
                return float("-inf")
            
            frame, _ = self.analyse_video_info(video_info)
            if frame is None:
                return float("-inf")
            
            return frame
        except Exception as e:
            print(f"❌ 流媒体速度检查错误 {url_info[0]}: {e}")
            return float("-inf")
    
    async def getSpeed(self, url_info):
        """获取速度"""
        try:
            url, _, _ = url_info
            if not url or not url.strip():
                return float("-inf")
                
            if "$" in url:
                url = url.split('$')[0]
            url = quote(url, safe=':/?&=$[]')
            url_info[0] = url
            
            speed = await self.check_stream_speed(url_info)
            return speed
        except Exception as e:
            print(f"❌ 获取速度错误 {url_info[0] if url_info else 'Unknown'}: {e}")
            return float("-inf")
    
    async def limited_getSpeed(self, url_info, semaphore):
        """限速获取速度"""
        async with semaphore:
            return await self.getSpeed(url_info)
    
    async def compareSpeedAndResolution(self, infoList):
        """比较速度和分辨率"""
        if not infoList:
            return None
        
        semaphore = asyncio.Semaphore(self.config.max_concurrent_tasks)
        
        try:
            response_times = await asyncio.gather(
                *[self.limited_getSpeed(url_info, semaphore) for url_info in infoList],
                return_exceptions=True
            )
        except Exception as e:
            print(f"❌ 测速任务执行错误: {e}")
            return None
        
        # 处理异常情况
        valid_responses = []
        for info, rt in zip(infoList, response_times):
            if isinstance(rt, Exception):
                print(f"⚠ 测速异常: {rt}")
                continue
            if rt != float("-inf"):
                valid_responses.append((info, rt))

        def extract_resolution(resolution_str):
            """提取分辨率数值"""
            if not resolution_str:
                return 0
            try:
                numbers = re.findall(r"\d+x\d+", resolution_str)
                if numbers:
                    width, height = map(int, numbers[0].split("x"))
                    return width * height
            except (ValueError, IndexError):
                pass
            return 0

        # 验证权重配置
        response_time_weight = max(0, min(1, getattr(self.config, "response_time_weight", 0.5)))
        resolution_weight = max(0, min(1, getattr(self.config, "resolution_weight", 0.5)))
        
        # 归一化权重
        total_weight = response_time_weight + resolution_weight
        if total_weight == 0:
            response_time_weight = 0.5
            resolution_weight = 0.5
        else:
            response_time_weight /= total_weight
            resolution_weight /= total_weight

        def combined_key(item):
            """组合排序键"""
            try:
                (_, _, resolution), response_time = item
                resolution_value = extract_resolution(resolution) if resolution else 0
                return (
                    response_time_weight * response_time +
                    resolution_weight * resolution_value
                )
            except Exception:
                return float("-inf")

        try:
            sorted_res = sorted(valid_responses, key=combined_key, reverse=True)
            return sorted_res
        except Exception as e:
            print(f"❌ 排序错误: {e}")
            return valid_responses
    
    def getTotalUrls(self, data):
        """获取总URL - 限制为8个"""
        if not data:
            return []
        try:
            max_urls = min(self.config.max_urls_per_channel, 8)  # 确保最多8个
            if len(data) > max_urls:
                total_urls = [url for (url, _, _), _ in data[:max_urls]]
            else:
                total_urls = [url for (url, _, _), _ in data]
            return list(dict.fromkeys(total_urls))
        except Exception as e:
            print(f"❌ 获取URL列表错误: {e}")
            return []
    
    def getTotalUrlsFromInfoList(self, infoList):
        """从信息列表获取总URL - 限制为8个"""
        if not infoList:
            return []
        try:
            max_urls = min(self.config.max_urls_per_channel, 8)  # 确保最多8个
            total_urls = [
                url for url, _, _ in infoList[:max_urls]
            ]
            return list(dict.fromkeys(total_urls))
        except Exception as e:
            print(f"❌ 从信息列表获取URL错误: {e}")
            return []
    
    def is_ipv6(self, url):
        """检查是否为IPv6"""
        try:
            host = urllib.parse.urlparse(url).hostname
            if host:
                ipaddress.IPv6Address(host)
                return True
            return False
        except (ValueError, ipaddress.AddressValueError):
            return False
    
    def checkUrlIPVType(self, url):
        """检查URL IP类型"""
        ipv_type = getattr(self.config, "ipv_type", "ipv4")
        if ipv_type == "ipv4":
            return not self.is_ipv6(url)
        elif ipv_type == "ipv6":
            return self.is_ipv6(url)
        else:
            return True
    
    def checkByDomainBlacklist(self, url):
        """检查域名黑名单"""
        try:
            domain_blacklist = [
                urlparse(domain).netloc if urlparse(domain).scheme else domain
                for domain in getattr(self.config, "domain_blacklist", [])
            ]
            return urlparse(url).netloc not in domain_blacklist
        except Exception:
            return True
    
    def checkByURLKeywordsBlacklist(self, url):
        """检查URL关键词黑名单"""
        try:
            url_keywords_blacklist = getattr(self.config, "url_keywords_blacklist", [])
            return not any(keyword in url for keyword in url_keywords_blacklist)
        except Exception:
            return True
    
    def filterUrlsByPatterns(self, urls):
        """根据模式过滤URL"""
        if not urls:
            return []
        filtered_urls = []
        for url in urls:
            if not url or not url.strip():
                continue
            if not self.checkUrlIPVType(url):
                continue
            if not self.checkByDomainBlacklist(url):
                continue
            if not self.checkByURLKeywordsBlacklist(url):
                continue
            filtered_urls.append(url)
        return filtered_urls
    
    def filter_CCTV_key(self, key: str):
        """过滤CCTV关键词"""
        if not key:
            return key
        try:
            key = re.sub(r'\[.*?\]', '', key)
            if "cctv" not in key.lower():
                return key.strip()
            chinese_pattern = re.compile("[\u4e00-\u9fa5]+")
            filtered_text = chinese_pattern.sub('', key)
            result = re.sub(r'\[\d+\*\d+\]', '', filtered_text)
            if "-" not in result:
                result = result.replace("CCTV", "CCTV-")
            if result.upper().endswith("HD"):
                result = result[:-2]
            return result.strip()
        except Exception:
            return key
    
    async def ffmpeg_url(self, url, timeout, cmd='ffmpeg'):
        """FFmpeg URL测试"""
        if not url or not url.strip():
            return None
            
        args = [cmd, '-t', str(timeout), '-stats', '-i', url, '-f', 'null', '-']
        proc = None
        res = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout + 5)
            if out:
                res = out.decode('utf-8', errors='ignore')
            if err:
                res = err.decode('utf-8', errors='ignore')
            return res
        except asyncio.TimeoutError:
            if proc:
                try:
                    proc.kill()
                except:
                    pass
            return None
        except Exception:
            if proc:
                try:
                    proc.kill()
                except:
                    pass
            return None
        finally:
            if proc:
                try:
                    await proc.wait()
                except:
                    pass
    
    def analyse_video_info(self, video_info):
        """分析视频信息"""
        frame_size = float("-inf")
        if video_info is not None:
            try:
                info_data = video_info.replace(" ", "")
                matches = re.findall(r"frame=(\d+).*?fps=([\d\.]+).*?speed=([\d\.]+)x", info_data)
                if matches:
                    total_frame = 0
                    total_fps = 0.0
                    total_speed = 0.0
                    count = 0
                    for m in matches:
                        try:
                            frame = int(m[0])
                            fps = float(m[1])
                            speed = float(m[2])
                            total_frame += frame
                            total_fps += fps
                            total_speed += speed
                            count += 1
                        except (ValueError, IndexError):
                            continue
                    if count > 0:
                        avg_frame = total_frame / count
                        avg_fps = total_fps / count
                        avg_speed = total_speed / count
                        frame_size = avg_frame + avg_fps + avg_speed
            except Exception:
                pass
        return frame_size, None
    
    def find_matching_values(self, dictionary, partial_key):
        """查找匹配值"""
        if not dictionary or not partial_key:
            return None
        result = []
        matching_keys = []
        try:
            for key in dictionary:
                if partial_key not in key:
                    continue
                if not key.replace(partial_key, ""):
                    matching_keys.append(key)
                elif key.replace(partial_key, "") in self.config.search_ignore_key:
                    matching_keys.append(key)
            if not matching_keys:
                return None
            for m_key in matching_keys:
                if m_key in dictionary:
                    result.extend(dictionary[m_key])
        except Exception as e:
            print(f"❌ 查找匹配值错误: {e}")
        return result if result else None
    
    def get_previous_results(self, file_path):
        """获取先前结果"""
        channel_dict = {}
        if not os.path.exists(file_path):
            return channel_dict
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                lines = file.readlines()
                for line in lines:
                    if "#genre#" in line:
                        continue
                    parts = line.strip().split(',')
                    if len(parts) == 2:
                        channel_name, url = parts
                        if channel_name and url:
                            if channel_name in channel_dict:
                                channel_dict[channel_name].append(url)
                            else:
                                channel_dict[channel_name] = [url]
        except Exception as e:
            print(f"❌ 读取先前结果错误: {e}")
        return channel_dict

# ==================== 增强的爬取和搜索功能 ====================
class IPTVCrawler:
    """IPTV爬取器 - 增强版"""
    
    def __init__(self, config, processor):
        self.config = config
        self.processor = processor
        self.rtp_paths = []
    
    def extract_rtp_paths(self):
        """从search_dict中提取RTP路径"""
        rtp_paths = []
        for region, url in self.config.search_dict.items():
            try:
                print(f"📡 提取RTP路径从: {region}")
                response = requests.get(url, timeout=15)
                if response.status_code == 200:
                    content = response.text
                    lines = content.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line.startswith('rtp://') or 'rtp://' in line:
                            rtp_match = re.search(r'rtp://[^/]+(/.*)', line)
                            if rtp_match:
                                path = rtp_match.group(1)
                                if path not in rtp_paths:
                                    rtp_paths.append(path)
                                    print(f"  ✅ 找到RTP路径: {path}")
                else:
                    print(f"  ❌ HTTP错误: {response.status_code}")
            except Exception as e:
                print(f"❌ 提取RTP路径失败 {region}: {e}")
        
        print(f"📊 总共提取到 {len(rtp_paths)} 个RTP路径")
        return rtp_paths
    
    def crawl_tonkiang_all_multicast(self, page_num=5):
        """从tonkiang.us爬取所有组播源（不指定关键词）"""
        print("🌐 爬取tonkiang.us所有组播源...")
        ip_headers = []
        
        for page in range(1, page_num + 1):
            try:
                # 访问组播页面
                url = f"http://tonkiang.us/hotellist.html?page={page}"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                response = requests.get(url, headers=headers, timeout=15)
                if response.status_code != 200:
                    print(f"  ❌ 第{page}页HTTP错误: {response.status_code}")
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                channel_divs = soup.find_all('div', class_='channel')
                
                for div in channel_divs:
                    try:
                        result_div = div.find('div', class_='result')
                        if not result_div:
                            continue
                        
                        # 查找IP头信息
                        ip_pattern = r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+)\b'
                        matches = re.findall(ip_pattern, result_div.get_text())
                        
                        for match in matches:
                            if match not in ip_headers:
                                ip_headers.append(match)
                    
                    except Exception as e:
                        continue
                
                print(f"  📄 第{page}页找到 {len(channel_divs)} 个频道，IP头总数: {len(ip_headers)}")
                
                # 检查是否有下一页
                if not channel_divs:
                    break
                    
            except Exception as e:
                print(f"❌ 爬取tonkiang.us第{page}页错误: {e}")
                continue
        
        print(f"📊 总共找到 {len(ip_headers)} 个IP头")
        return ip_headers
    
    def crawl_tonkiang_by_region(self, region, page_num=5):
        """从tonkiang.us按地区爬取组播源"""
        print(f"🌐 爬取tonkiang.us地区组播源: {region}")
        ip_headers = []
        
        for page in range(1, page_num + 1):
            try:
                # 使用地区作为搜索关键词
                url = f"http://tonkiang.us/hotellist.html?s={quote(region)}&page={page}"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                response = requests.get(url, headers=headers, timeout=15)
                if response.status_code != 200:
                    print(f"  ❌ 地区{region}第{page}页HTTP错误: {response.status_code}")
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                channel_divs = soup.find_all('div', class_='channel')
                
                for div in channel_divs:
                    try:
                        result_div = div.find('div', class_='result')
                        if not result_div:
                            continue
                        
                        # 查找IP头信息
                        ip_pattern = r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+)\b'
                        matches = re.findall(ip_pattern, result_div.get_text())
                        
                        for match in matches:
                            if match not in ip_headers:
                                ip_headers.append(match)
                    
                    except Exception as e:
                        continue
                
                print(f"  📄 地区{region}第{page}页找到 {len(channel_divs)} 个频道，IP头总数: {len(ip_headers)}")
                
                if not channel_divs:
                    break
                    
            except Exception as e:
                print(f"❌ 爬取地区{region}第{page}页错误: {e}")
                continue
        
        print(f"📊 地区{region}总共找到 {len(ip_headers)} 个IP头")
        return ip_headers
    
    def combine_rtp_urls(self, ip_headers, rtp_paths):
        """组合RTP URL：将IP头与RTP路径拼接成完整URL"""
        combined_urls = []
        
        for ip_header in ip_headers:
            for path in rtp_paths:
                full_url = f"http://{ip_header}/rtp{path}"
                combined_urls.append(full_url)
        
        return combined_urls
    
    def get_crawl_result(self):
        """获取爬取结果 - 增强版"""
        print("🚀 开始爬取直播源...")
        crawl_result_dict = {}
        
        # 提取RTP路径
        rtp_paths = self.extract_rtp_paths()
        self.rtp_paths = rtp_paths
        
        if self.config.crawl_type in ["1", "3"] and rtp_paths:
            print("🔍 增强tonkiang.us组播源爬取...")
            
            # 获取搜索地区配置
            search_regions = getattr(self.config, 'search_regions', ["全国"])
            all_ip_headers = []
            
            # 按配置的地区进行搜索
            for region in search_regions:
                if region == "全国":
                    # 搜索所有组播源
                    region_ips = self.crawl_tonkiang_all_multicast(self.config.search_page_num)
                else:
                    # 搜索指定地区
                    region_ips = self.crawl_tonkiang_by_region(region, self.config.search_page_num)
                
                all_ip_headers.extend(region_ips)
                print(f"📍 地区 {region} 找到 {len(region_ips)} 个IP头")
            
            # 去重
            all_ip_headers = list(set(all_ip_headers))
            print(f"📊 所有地区总共找到 {len(all_ip_headers)} 个唯一IP头")
            
            if all_ip_headers:
                # 组合RTP URL
                combined_rtp_urls = self.combine_rtp_urls(all_ip_headers, rtp_paths)
                print(f"🔗 生成 {len(combined_rtp_urls)} 个组合RTP URL")
                
                # 将组合的URL分配到对应频道
                channels = self.processor.getChannelItems()
                for category, channel_dict in channels.items():
                    for channel_name in channel_dict.keys():
                        filtered_name = self.processor.filter_CCTV_key(channel_name)
                        if filtered_name:
                            # 为每个频道分配一部分组合URL
                            if channel_name not in crawl_result_dict:
                                crawl_result_dict[channel_name] = []
                            
                            # 随机选择一部分URL分配给该频道（避免每个频道都有全部URL）
                            sample_size = min(8, len(combined_rtp_urls))  # 每个频道最多8个URL
                            if sample_size > 0 and combined_rtp_urls:
                                sampled_urls = random.sample(combined_rtp_urls, sample_size)
                                crawl_result_dict[channel_name].extend(sampled_urls)
                
                print(f"📺 为 {len(crawl_result_dict)} 个频道分配了组合RTP URL")
        
        if self.config.crawl_type in ["2", "3"]:
            print("🌐 爬取配置的URL源...")
            for url in self.config.crawl_urls:
                try:
                    print(f"  📡 爬取: {url}")
                    response = requests.get(url, timeout=15)
                    if response.status_code == 200:
                        content = response.text
                        lines = content.split('\n')
                        url_count = 0
                        for line in lines:
                            line = line.strip()
                            if ',' in line and '#genre#' not in line:
                                parts = line.split(',', 1)
                                if len(parts) == 2:
                                    channel, url_val = parts[0].strip(), parts[1].strip()
                                    if channel and url_val:
                                        if channel not in crawl_result_dict:
                                            crawl_result_dict[channel] = []
                                        if url_val not in crawl_result_dict[channel]:
                                            crawl_result_dict[channel].append(url_val)
                                            url_count += 1
                        print(f"  ✅ 成功爬取 {url_count} 个URL")
                    else:
                        print(f"  ❌ HTTP错误: {response.status_code}")
                except Exception as e:
                    print(f"❌ 爬取失败 {url}: {e}")
        
        print(f"🎉 爬取完成，共获取 {len(crawl_result_dict)} 个频道")
        return crawl_result_dict
    
    def search_hotel_ip(self):
        """搜索酒店IP"""
        print("🏨 搜索酒店IP...")
        subscribe_dict = {}
        
        # 从订阅源获取直播源
        for region, url in self.config.search_dict.items():
            try:
                print(f"  📡 加载订阅源: {region}")
                response = requests.get(url, timeout=15)
                if response.status_code == 200:
                    content = response.text
                    lines = content.split('\n')
                    url_count = 0
                    for line in lines:
                        line = line.strip()
                        if ',' in line and '#genre#' not in line:
                            parts = line.split(',', 1)
                            if len(parts) == 2:
                                channel, url_val = parts[0].strip(), parts[1].strip()
                                if channel and url_val:
                                    if channel not in subscribe_dict:
                                        subscribe_dict[channel] = []
                                    if url_val not in subscribe_dict[channel]:
                                        subscribe_dict[channel].append(url_val)
                                        url_count += 1
                    print(f"  ✅ 成功加载 {region} 订阅源，{url_count} 个URL")
                else:
                    print(f"  ❌ HTTP错误: {response.status_code}")
            except Exception as e:
                print(f"❌ 加载订阅源失败 {region}: {e}")
        
        # 生成搜索关键词 - 严格按照模板频道列表
        search_keyword_list = []
        channels = self.processor.getChannelItems()
        for category, channel_dict in channels.items():
            for channel_name in channel_dict.keys():
                filtered_name = self.processor.filter_CCTV_key(channel_name)
                if filtered_name:
                    search_keyword_list.append(filtered_name)
        
        print(f"🔍 搜索完成，共 {len(search_keyword_list)} 个搜索关键词")
        return subscribe_dict, {}, search_keyword_list

# ==================== 主更新类 ====================
class UpdateSource:
    """更新源主类"""
    
    def __init__(self, crawl_result_dict, subscribe_dict, kw_zbip_dict, search_keyword_list):
        self.config = DynamicConfig()
        self.processor = IPTVProcessor(self.config)
        self.crawl_result_dict = crawl_result_dict
        self.subscribe_dict = subscribe_dict
        self.kw_zbip_dict = kw_zbip_dict
        self.search_keyword_list = search_keyword_list
    
    async def process_channel_urls(self, channel_name, filtered_name):
        """处理单个频道的URL - 所有找到的URL都进行测速"""
        # 收集所有可能的URL源
        all_urls = []
        
        # 1. 从爬取结果获取URL（组合的RTP URL）
        if filtered_name and filtered_name in self.crawl_result_dict:
            all_urls.extend(self.crawl_result_dict[filtered_name])
        
        # 2. 从订阅源获取URL
        if filtered_name:
            matching_urls = self.processor.find_matching_values(self.subscribe_dict, filtered_name)
            if matching_urls:
                all_urls.extend(matching_urls)
        
        # 过滤URL
        filtered_urls = self.processor.filterUrlsByPatterns(all_urls)
        
        best_urls = []
        if filtered_urls:
            # 准备测速 - 所有URL都进行测速
            info_list = [[url, None, None] for url in filtered_urls]
            
            print(f"  ⚡ 对 {len(info_list)} 个URL进行测速排序...")
            try:
                # 异步测速排序
                sorted_data = await self.processor.compareSpeedAndResolution(info_list)
                if sorted_data:
                    best_urls = self.processor.getTotalUrls(sorted_data)
                else:
                    best_urls = self.processor.getTotalUrlsFromInfoList(info_list)
            except Exception as e:
                print(f"❌ 测速排序错误: {e}")
                best_urls = self.processor.getTotalUrlsFromInfoList(info_list)
            
            # 确保最多8个URL
            best_urls = best_urls[:8]
            print(f"  ✅ 测速完成，选择 {len(best_urls)} 个最佳源")
        
        return best_urls
    
    async def main(self):
        """主执行函数 - 严格按照模板频道列表"""
        print("🚀 开始更新直播源...")
        start_time = time.time()
        
        try:
            # 清理旧文件
            if os.path.exists("result_new.txt"):
                os.remove("result_new.txt")
            
            # 获取频道数据 - 严格按照模板
            channels = self.processor.getChannelItems()
            if not channels:
                print("❌ 错误: 无法读取频道数据")
                return
            
            total_channels = sum(len(channel_dict) for channel_dict in channels.values())
            processed_channels = 0
            
            print(f"📺 开始处理 {total_channels} 个频道...")
            print("📋 严格按照模板频道列表进行搜索和测速...")
            
            # 按照模板分类顺序处理
            for category, channel_dict in channels.items():
                print(f"\n🏷️ 处理分类: {category}")
                category_channels = {}
                
                # 按照模板频道顺序处理
                for channel_name in channel_dict.keys():
                    processed_channels += 1
                    print(f"  📻 处理频道 [{processed_channels}/{total_channels}]: {channel_name}")
                    
                    filtered_name = self.processor.filter_CCTV_key(channel_name)
                    best_urls = await self.process_channel_urls(channel_name, filtered_name)
                    
                    if best_urls:
                        category_channels[channel_name] = best_urls
                        print(f"    ✅ 找到 {len(best_urls)} 个可用源")
                    else:
                        print(f"    ⚠ 未找到可用源")
                        category_channels[channel_name] = []  # 即使没有源也保留频道
                
                # 更新分类结果 - 严格按照模板顺序
                if category_channels:
                    self.processor.updateChannelUrlsTxt(category, category_channels)
                    print(f"✅ 分类 {category} 处理完成，共 {len(category_channels)} 个频道")
            
            # 完成文件更新
            self.processor.updateFile(self.config.final_file, "result_new.txt")
            
            end_time = time.time()
            processing_time = end_time - start_time
            print(f"\n🎉 更新完成！耗时: {processing_time:.2f} 秒")
            print(f"💾 结果文件: {self.config.final_file}")
            
            # 显示统计信息
            self.show_statistics()
            
        except Exception as e:
            print(f"❌ 更新过程中出现错误: {e}")
            traceback.print_exc()
    
    def show_statistics(self):
        """显示统计信息"""
        if os.path.exists(self.config.final_file):
            try:
                with open(self.config.final_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                lines = content.split('\n')
                channel_count = 0
                url_count = 0
                categories = []
                
                for line in lines:
                    if line.strip() and '#genre#' in line:
                        categories.append(line.replace(',#genre#', ''))
                    elif line.strip() and '#genre#' not in line and ',' in line:
                        channel_count += 1
                        url_count += 1
                
                print(f"\n📊 最终结果统计:")
                print(f"  📁 分类数量: {len(categories)}")
                print(f"  📺 频道数量: {channel_count}")
                print(f"  🔗 URL数量: {url_count}")
                print(f"  🏷️ 分类列表: {', '.join(categories)}")
            except Exception as e:
                print(f"❌ 统计信息显示错误: {e}")
        else:
            print("⚠ 结果文件不存在")

# ==================== 主函数 ====================
async def main():
    """主函数"""
    print("=" * 70)
    print("🎬 IPTV直播源管理工具 - 增强RTP组合版")
    print("✨ 特点:")
    print("  • 📋 严格按照模板频道列表搜索")
    print("  • ⚡ 所有找到的URL都进行测速") 
    print("  • 📊 按照模板顺序生成结果文件")
    print("  • 🎯 每个频道最多8个优质源")
    print("  • 🔧 集成配置，无需外部文件")
    print("=" * 70)
    
    # 检查ffmpeg是否可用
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5, text=True)
        if result.returncode == 0:
            print("✅ FFmpeg可用")
        else:
            print("⚠ FFmpeg可能不可用，将影响流媒体测速")
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        print("⚠ 警告: FFmpeg不可用，将影响流媒体测速")
    
    # 执行更新
    try:
        config = DynamicConfig()
        processor = IPTVProcessor(config)
        crawler = IPTVCrawler(config, processor)
        
        processor.previous_result_dict = processor.get_previous_results(config.final_file)
        crawl_result_dict = crawler.get_crawl_result()
        subscribe_dict, kw_zbip_dict, search_keyword_list = crawler.search_hotel_ip()
        
        update_source = UpdateSource(crawl_result_dict, subscribe_dict, kw_zbip_dict, search_keyword_list)
        await update_source.main()
    except Exception as e:
        print(f"❌ 程序执行错误: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断程序执行")
    except Exception as e:
        print(f"❌ 程序运行错误: {e}")
        traceback.print_exc()
