import requests
import pandas as pd
import re
import os
import time
import subprocess
import json
from typing import List, Dict, Optional, Tuple, Any
from urllib.parse import urlparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

class IPTVCrawler:
    def __init__(self):
        # 配置文件
        self.config = {
            # 网络源开关
            "enable_online_sources": True,
            # 本地源开关
            "enable_local_sources": True,
            # 黑名单开关
            "enable_blacklist": True,
            # IPv6过滤开关
            "enable_ipv6_filter": True,
            # FFmpeg测速开关
            "enable_ffmpeg_test": True,
            # FFmpeg测速超时时间（秒）
            "ffmpeg_timeout": 5,
            # 权重配置
            "speed_weight": 0.5,      # 速度权重
            "response_weight": 0.5,   # 响应时间权重
            # 每个频道最大源数量
            "max_sources_per_channel": 8,
            # 并发线程数
            "max_workers": 10,
            # 频道名称匹配相似度阈值
            "match_threshold": 0.7,
        }
        
        self.urls = [
            "https://raw.githubusercontent.com/Supprise0901/TVBox_live/main/live.txt",
            "https://raw.githubusercontent.com/wwb521/live/main/tv.m3u",
            "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/ipv4/result.m3u",  
            "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
            "https://raw.githubusercontent.com/suxuang/myIPTV/main/ipv4.m3u",
            "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/iptv4.txt",
            "https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt",
            "http://47.120.41.246:8899/zb.txt",
        ]
        
        self.local_source = "local.txt"
        self.template_file = "demo.txt"
        self.blacklist_file = "blacklist.txt"
        self.output_txt = "iptv.txt"
        self.output_m3u = "iptv.m3u"
        self.config_file = "config.json"
        
        self.ipv4_pattern = re.compile(r'^https?://(\d{1,3}\.){3}\d{1,3}')
        self.ipv6_pattern = re.compile(r'^https?://\[([a-fA-F0-9:]+)\]')
        
        # 常见后缀模式
        self.suffix_patterns = [
            r'\s*高清$', r'\s*HD$', r'\s*hd$', r'\s*标清$', r'\s*SD$', r'\s*sd$',
            r'\s*超清$', r'\s*FHD$', r'\s*fhd$', r'\s*4K$', r'\s*4k$', r'\s*8K$', r'\s*8k$',
            r'\s*综合$', r'\s*财经$', r'\s*体育$', r'\s*影视$', r'\s*新闻$', r'\s*科教$',
            r'\s*戏曲$', r'\s*音乐$', r'\s*少儿$', r'\s*农业$', r'\s*军事$',
            r'\s*\(\d+\)$', r'\s*\[\d+\]$',  # 去除数字后缀
            r'\s*直播$', r'\s*LIVE$', r'\s*live$',
            r'\s*频道$', r'\s*CH$', r'\s*ch$', r'\s*TV$', r'\s*tv$',
        ]
        
        # 频道名称映射规则
        self.channel_mappings = {
            r'cctv[_\-\s]*1': 'CCTV-1',
            r'cctv[_\-\s]*2': 'CCTV-2',
            r'cctv[_\-\s]*3': 'CCTV-3',
            r'cctv[_\-\s]*4': 'CCTV-4',
            r'cctv[_\-\s]*5': 'CCTV-5',
            r'cctv[_\-\s]*6': 'CCTV-6',
            r'cctv[_\-\s]*7': 'CCTV-7',
            r'cctv[_\-\s]*8': 'CCTV-8',
            r'cctv[_\-\s]*9': 'CCTV-9',
            r'cctv[_\-\s]*10': 'CCTV-10',
            r'cctv[_\-\s]*11': 'CCTV-11',
            r'cctv[_\-\s]*12': 'CCTV-12',
            r'cctv[_\-\s]*13': 'CCTV-13',
            r'cctv[_\-\s]*14': 'CCTV-14',
            r'cctv[_\-\s]*15': 'CCTV-15',
            r'cctv[_\-\s]*16': 'CCTV-16',
            r'cctv[_\-\s]*17': 'CCTV-17',
            r'湖南卫视': '湖南卫视',
            r'湖南电视台': '湖南卫视',
            r'hunan': '湖南卫视',
            r'浙江卫视': '浙江卫视',
            r'zhejiang': '浙江卫视',
            r'江苏卫视': '江苏卫视',
            r'jiangsu': '江苏卫视',
            r'北京卫视': '北京卫视',
            r'beijing': '北京卫视',
            r'东方卫视': '东方卫视',
            r'dongfang': '东方卫视',
            r'安徽卫视': '安徽卫视',
            r'anhui': '安徽卫视',
        }
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # 初始化数据
        self.template_structure = []
        self.blacklist = []
        self.local_streams = []
        
        # 加载配置和数据
        self.load_config()
        self.load_all_data()

    def load_all_data(self):
        """加载所有必要的数据"""
        try:
            self.template_structure = self.load_template_structure()
            self.blacklist = self.load_blacklist() if self.config["enable_blacklist"] else []
            self.local_streams = self.load_local_streams() if self.config["enable_local_sources"] else []
        except Exception as e:
            print(f"加载数据时出错: {e}")

    def load_config(self):
        """加载配置文件"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    # 更新配置
                    for key, value in user_config.items():
                        if key in self.config:
                            self.config[key] = value
                print(f"加载配置文件: {self.config_file}")
            except Exception as e:
                print(f"加载配置文件失败: {e}，使用默认配置")
        else:
            print("配置文件不存在，使用默认配置")
            self.save_config()
        
        # 验证配置
        self._validate_config()
        
        print("当前配置:")
        for key, value in self.config.items():
            print(f"  {key}: {value}")

    def _validate_config(self):
        """验证配置参数"""
        if not 0 <= self.config["speed_weight"] <= 1:
            print("警告: speed_weight 必须在 0-1 之间，已重置为 0.5")
            self.config["speed_weight"] = 0.5
        
        if not 0 <= self.config["response_weight"] <= 1:
            print("警告: response_weight 必须在 0-1 之间，已重置为 0.5")
            self.config["response_weight"] = 0.5
        
        if abs(self.config["speed_weight"] + self.config["response_weight"] - 1.0) > 0.01:
            print("警告: 速度权重和响应权重之和必须为1，已自动调整")
            total = self.config["speed_weight"] + self.config["response_weight"]
            self.config["speed_weight"] = self.config["speed_weight"] / total
            self.config["response_weight"] = self.config["response_weight"] / total

    def save_config(self):
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            print(f"配置文件已保存: {self.config_file}")
        except Exception as e:
            print(f"保存配置文件失败: {e}")

    def normalize_channel_name(self, name: str) -> str:
        """
        标准化频道名称，去除常见后缀并应用映射规则
        """
        if not name or not isinstance(name, str):
            return ""
            
        original_name = name.strip()
        if not original_name:
            return ""
        
        # 首先应用映射规则
        normalized = original_name
        for pattern, replacement in self.channel_mappings.items():
            if re.search(pattern, normalized, re.IGNORECASE):
                normalized = replacement
                break
        
        # 去除常见后缀
        for pattern in self.suffix_patterns:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
        
        # 去除多余空格
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # 特殊处理：确保CCTV频道格式统一
        normalized = re.sub(r'CCTV[_\-\s]*(\d+)', r'CCTV-\1', normalized, flags=re.IGNORECASE)
        
        # 如果标准化后为空，返回原名称
        return normalized if normalized else original_name

    def calculate_similarity(self, name1: str, name2: str) -> float:
        """
        计算两个频道名称的相似度
        """
        if not name1 or not name2:
            return 0.0
            
        name1_norm = self.normalize_channel_name(name1).lower()
        name2_norm = self.normalize_channel_name(name2).lower()
        
        # 完全匹配
        if name1_norm == name2_norm:
            return 1.0
        
        # 包含关系
        if name1_norm in name2_norm or name2_norm in name1_norm:
            return 0.9
        
        # 计算编辑距离相似度
        def edit_distance(s1, s2):
            if len(s1) < len(s2):
                return edit_distance(s2, s1)
            if len(s2) == 0:
                return len(s1)
            previous_row = range(len(s2) + 1)
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row
            return previous_row[-1]
        
        try:
            distance = edit_distance(name1_norm, name2_norm)
            max_len = max(len(name1_norm), len(name2_norm))
            similarity = 1 - (distance / max_len) if max_len > 0 else 0
            return similarity
        except:
            return 0.0

    def find_best_template_match(self, channel_name: str, template_channels: List[str]) -> Optional[str]:
        """
        为频道名称找到最佳模板匹配
        """
        if not channel_name or not template_channels:
            return None
            
        normalized_channel = self.normalize_channel_name(channel_name)
        
        # 首先尝试完全匹配
        for template_channel in template_channels:
            if self.normalize_channel_name(template_channel) == normalized_channel:
                return template_channel
        
        # 然后尝试相似度匹配
        best_match = None
        best_similarity = 0
        
        for template_channel in template_channels:
            similarity = self.calculate_similarity(channel_name, template_channel)
            if similarity > best_similarity and similarity >= self.config["match_threshold"]:
                best_similarity = similarity
                best_match = template_channel
        
        return best_match

    def load_template_structure(self) -> List[Dict]:
        """加载模板结构，只包含频道名称（不含URL）"""
        template_structure = []
        current_genre = ""
        
        if not os.path.exists(self.template_file):
            print(f"警告: 模板文件 {self.template_file} 不存在")
            return template_structure
        
        try:
            with open(self.template_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 检查是否是分类行
                    if line.endswith(',#genre#'):
                        current_genre = line.replace(',#genre#', '')
                        template_structure.append({
                            "type": "genre",
                            "name": current_genre
                        })
                    # 频道行 (只包含频道名称，不含URL)
                    elif line and current_genre and not line.endswith(',#genre#'):
                        # 如果行包含逗号，只取频道名称部分
                        if ',' in line:
                            channel_name = line.split(',')[0].strip()
                        else:
                            channel_name = line
                        
                        if not channel_name:
                            continue
                            
                        # 标准化模板中的频道名称
                        normalized_name = self.normalize_channel_name(channel_name)
                        
                        template_structure.append({
                            "type": "channel",
                            "name": normalized_name,
                            "original_name": channel_name,  # 保留原始名称用于输出
                            "genre": current_genre
                        })
            
            # 统计模板中的频道
            template_channels = [item for item in template_structure if item['type'] == 'channel']
            
            print(f"加载模板结构: {len([x for x in template_structure if x['type'] == 'genre'])} 个分类, "
                  f"{len(template_channels)} 个频道")
                  
            # 显示模板频道示例
            if template_channels:
                print("模板频道示例:")
                for channel in template_channels[:5]:
                    print(f"  {channel['name']}")
            else:
                print("警告: 模板文件中没有找到任何频道")
                
        except Exception as e:
            print(f"加载模板文件时出错: {e}")
            
        return template_structure

    def load_blacklist(self) -> List[str]:
        """加载黑名单"""
        blacklist = []
        if not os.path.exists(self.blacklist_file):
            print(f"提示: 黑名单文件 {self.blacklist_file} 不存在")
            return blacklist
            
        try:
            with open(self.blacklist_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        blacklist.append(line)
            print(f"加载黑名单: {len(blacklist)} 个关键词")
        except Exception as e:
            print(f"加载黑名单文件时出错: {e}")
            
        return blacklist

    def load_local_streams(self) -> List[Dict[str, str]]:
        """加载本地源"""
        streams = []
        if not os.path.exists(self.local_source):
            print(f"提示: 本地源文件 {self.local_source} 不存在")
            return streams
            
        try:
            with open(self.local_source, 'r', encoding='utf-8') as f:
                current_genre = ""
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 检查是否是分类行
                    if line.endswith(',#genre#'):
                        current_genre = line.replace(',#genre#', '')
                        continue
                    
                    # 解析频道行
                    if ',' in line and not line.endswith(',#genre#'):
                        parts = line.split(',', 1)
                        if len(parts) == 2:
                            program_name = parts[0].strip()
                            stream_url = parts[1].strip()
                            
                            if not program_name or not stream_url:
                                continue
                                
                            # 标准化频道名称
                            normalized_name = self.normalize_channel_name(program_name)
                            
                            # 添加到本地流
                            streams.append({
                                "program_name": normalized_name,
                                "original_name": program_name,  # 保留原始名称
                                "stream_url": stream_url,
                                "genre": current_genre,
                                "source": "local"
                            })
            
            print(f"加载本地源: {len(streams)} 个频道")
        except Exception as e:
            print(f"加载本地源文件时出错: {e}")
            
        return streams

    def is_blacklisted(self, url: str) -> bool:
        """检查URL是否在黑名单中"""
        if not self.config["enable_blacklist"] or not url:
            return False
            
        for keyword in self.blacklist:
            if keyword and keyword.lower() in url.lower():
                return True
        return False

    def parse_m3u(self, content: str) -> List[Dict[str, str]]:
        """解析M3U格式内容"""
        streams = []
        current_program = None
        
        if not content:
            return streams
            
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
                
            if line.startswith("#EXTINF"):
                current_program = self._extract_program_name(line)
                
            elif line.startswith(("http://", "https://")):
                if current_program and not self.is_blacklisted(line):
                    # IPv6过滤
                    if self.config["enable_ipv6_filter"] and self.ipv6_pattern.match(line):
                        continue
                    # IPv4检查
                    if not self.ipv4_pattern.match(line):
                        continue
                    
                    # 标准化频道名称
                    normalized_name = self.normalize_channel_name(current_program)
                    
                    streams.append({
                        "program_name": normalized_name,
                        "original_name": current_program,  # 保留原始名称
                        "stream_url": line,
                        "source": "online"
                    })
                current_program = None
                    
        return streams

    def parse_txt(self, content: str) -> List[Dict[str, str]]:
        """解析TXT格式内容"""
        streams = []
        
        if not content:
            return streams
            
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#') or line.endswith(',#genre#'):
                continue
                
            # 支持多种分隔符
            if match := re.match(r"(.+?)[,|\s]+\s*(https?://.+)", line):
                program_name = match.group(1).strip()
                stream_url = match.group(2).strip()
                
                if not program_name or not stream_url:
                    continue
                    
                if not self.is_blacklisted(stream_url):
                    # IPv6过滤
                    if self.config["enable_ipv6_filter"] and self.ipv6_pattern.match(stream_url):
                        continue
                    # IPv4检查
                    if not self.ipv4_pattern.match(stream_url):
                        continue
                    
                    # 标准化频道名称
                    normalized_name = self.normalize_channel_name(program_name)
                    
                    streams.append({
                        "program_name": normalized_name,
                        "original_name": program_name,  # 保留原始名称
                        "stream_url": stream_url,
                        "source": "online"
                    })
                
        return streams

    def _extract_program_name(self, extinf_line: str) -> str:
        """从EXTINF行提取节目名称"""
        if not extinf_line:
            return ""
            
        # 优先提取tvg-name
        if match := re.search(r'tvg-name="([^"]+)"', extinf_line):
            return match.group(1).strip()
        
        # 其次提取逗号后的名称
        if match := re.search(r',\s*(.+?)(?:\s*$|\s*http)', extinf_line):
            return match.group(1).strip()
            
        # 最后返回整个行
        return extinf_line.split(',')[-1].strip()

    def fetch_streams_from_url(self, url: str) -> Optional[str]:
        """从URL获取流数据"""
        if not self.config["enable_online_sources"] or not url:
            return None
            
        print(f"正在爬取: {url}")
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            
            # 自动检测编码
            if response.encoding.lower() == 'iso-8859-1':
                response.encoding = response.apparent_encoding or 'utf-8'
                
            return response.text
            
        except requests.exceptions.RequestException as e:
            print(f"请求失败 {url}: {e}")
            return None

    def fetch_all_streams(self) -> str:
        """获取所有源的流数据"""
        if not self.config["enable_online_sources"]:
            return ""
            
        all_streams = []
        successful_sources = 0
        
        for url in self.urls:
            if content := self.fetch_streams_from_url(url):
                all_streams.append(content)
                successful_sources += 1
            else:
                print(f"跳过来源: {url}")
            
            # 添加延迟避免请求过快
            time.sleep(1)
        
        print(f"成功获取 {successful_sources}/{len(self.urls)} 个网络源")
        return "\n".join(all_streams)

    def organize_streams(self, content: str) -> pd.DataFrame:
        """整理和去重流数据"""
        all_streams = self.local_streams.copy() if self.config["enable_local_sources"] else []
        
        if content:
            # 自动检测格式
            if content.startswith("#EXTM3U"):
                online_streams = self.parse_m3u(content)
            else:
                online_streams = self.parse_txt(content)
            
            all_streams.extend(online_streams)
            
        if not all_streams:
            print("未解析到任何流数据")
            return pd.DataFrame()
            
        try:
            df = pd.DataFrame(all_streams)
            print(f"解析到总流数: {len(df)} 个")
            
            # 去重 (基于节目名称和流URL)
            initial_count = len(df)
            df = df.drop_duplicates(subset=['program_name', 'stream_url'])
            print(f"去重后剩余: {len(df)} 个流 (移除 {initial_count - len(df)} 个重复项)")
            
            return df
        except Exception as e:
            print(f"整理流数据时出错: {e}")
            return pd.DataFrame()

    def test_stream_with_ffmpeg(self, stream_url: str) -> Dict[str, Any]:
        """使用FFmpeg测试流媒体速度和响应时间"""
        if not self.config["enable_ffmpeg_test"] or not stream_url:
            return {"speed_score": 1.0, "response_time": 0, "success": True}
            
        try:
            # 构建FFmpeg命令
            cmd = [
                'ffmpeg',
                '-i', stream_url,
                '-t', str(self.config["ffmpeg_timeout"]),  # 测试时长
                '-f', 'null', '-',  # 输出到空
                '-hide_banner',
                '-loglevel', 'error'
            ]
            
            start_time = time.time()
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL
            )
            
            # 等待进程完成或超时
            try:
                stdout, stderr = process.communicate(timeout=self.config["ffmpeg_timeout"] + 2)
                end_time = time.time()
                
                response_time = end_time - start_time
                
                # 分析FFmpeg输出获取速度信息
                output = stderr.decode('utf-8', errors='ignore')
                
                # 计算速度分数（基于比特率）
                speed_score = 0.5  # 默认分数
                bitrate_match = re.search(r'bitrate=\s*(\d+)\s*kb/s', output)
                if bitrate_match:
                    bitrate = int(bitrate_match.group(1))
                    # 比特率越高分数越高，最大2Mbps为满分
                    speed_score = min(bitrate / 2000, 1.0)
                
                # 响应时间分数（响应时间越短分数越高）
                response_score = max(0, 1 - (response_time / self.config["ffmpeg_timeout"]))
                
                # 综合分数
                total_score = (
                    speed_score * self.config["speed_weight"] + 
                    response_score * self.config["response_weight"]
                )
                
                return {
                    "speed_score": total_score,
                    "response_time": response_time,
                    "bitrate": int(bitrate_match.group(1)) if bitrate_match else 0,
                    "success": process.returncode == 0
                }
                
            except subprocess.TimeoutExpired:
                process.kill()
                return {"speed_score": 0, "response_time": self.config["ffmpeg_timeout"], "success": False}
                
        except Exception as e:
            return {"speed_score": 0, "response_time": 0, "success": False, "error": str(e)}

    def test_streams_batch(self, streams: List[Dict]) -> List[Dict]:
        """批量测试流媒体"""
        if not self.config["enable_ffmpeg_test"] or not streams:
            return streams
            
        print(f"开始FFmpeg测速，超时时间: {self.config['ffmpeg_timeout']}秒...")
        tested_streams = []
        
        with ThreadPoolExecutor(max_workers=self.config["max_workers"]) as executor:
            # 准备测试任务
            future_to_stream = {
                executor.submit(self.test_stream_with_ffmpeg, stream["stream_url"]): stream 
                for stream in streams if stream.get("stream_url")
            }
            
            # 处理完成的任务
            completed_count = 0
            total_count = len(future_to_stream)
            
            for future in as_completed(future_to_stream):
                stream = future_to_stream[future]
                try:
                    test_result = future.result()
                    stream.update(test_result)
                    tested_streams.append(stream)
                    
                    completed_count += 1
                    # 进度显示
                    if completed_count % 10 == 0 or completed_count == total_count:
                        print(f"测速进度: {completed_count}/{total_count}")
                        
                except Exception as e:
                    print(f"测试流 {stream.get('stream_url', '未知URL')} 时出错: {e}")
                    stream.update({"speed_score": 0, "success": False})
                    tested_streams.append(stream)
        
        return tested_streams

    def filter_and_sort_channels(self, df: pd.DataFrame) -> pd.DataFrame:
        """按照模板结构过滤和排序"""
        if df.empty or not self.template_structure:
            return df
            
        # 获取模板中的所有频道名称
        template_channels = [item['name'] for item in self.template_structure if item['type'] == 'channel']
        
        if not template_channels:
            print("错误: 模板中没有找到任何频道")
            return pd.DataFrame()
            
        print(f"模板频道数量: {len(template_channels)}")
        print(f"模板频道示例: {template_channels[:5]}")
        
        # 为每个流找到最佳模板匹配
        matched_streams = []
        unmatched_count = 0
        
        for _, stream in df.iterrows():
            program_name = stream.get('program_name', '')
            if not program_name:
                continue
                
            best_match = self.find_best_template_match(program_name, template_channels)
            if best_match:
                # 创建新的流记录，使用匹配到的模板频道名称
                new_stream = stream.copy()
                new_stream['template_channel'] = best_match
                matched_streams.append(new_stream)
            else:
                unmatched_count += 1
                # 显示未匹配的频道（用于调试）
                if unmatched_count <= 5:  # 只显示前5个未匹配的
                    print(f"未匹配频道: {program_name} (原始: {stream.get('original_name', 'N/A')})")
        
        if unmatched_count > 5:
            print(f"... 还有 {unmatched_count - 5} 个未匹配频道")
        
        if not matched_streams:
            print("错误: 没有找到任何匹配的频道")
            return pd.DataFrame()
            
        try:
            filtered_df = pd.DataFrame(matched_streams)
            print(f"匹配到模板的流: {len(filtered_df)} 个 (未匹配: {unmatched_count} 个)")
            
            # 显示匹配统计
            match_stats = filtered_df['template_channel'].value_counts()
            print(f"匹配频道数量: {len(match_stats)}")
            print("匹配最多的前10个频道:")
            for channel, count in match_stats.head(10).items():
                print(f"  {channel}: {count} 个源")
            
            # FFmpeg测速
            if self.config["enable_ffmpeg_test"]:
                print("开始FFmpeg测速...")
                streams_list = filtered_df.to_dict('records')
                tested_streams = self.test_streams_batch(streams_list)
                filtered_df = pd.DataFrame(tested_streams)
                
                # 统计测速结果
                successful_tests = len([s for s in tested_streams if s.get('success', False)])
                print(f"FFmpeg测速完成: {successful_tests}/{len(tested_streams)} 个流测试成功")
            
            # 为每个频道添加模板中的分类信息
            channel_genre_map = {}
            for item in self.template_structure:
                if item['type'] == 'channel':
                    channel_genre_map[item['name']] = item['genre']
            
            filtered_df['template_genre'] = filtered_df['template_channel'].map(channel_genre_map)
            
            # 按照模板顺序和测速分数排序
            channel_order = {name: idx for idx, name in enumerate(template_channels)}
            filtered_df['channel_order'] = filtered_df['template_channel'].map(channel_order)
            
            # 按频道分组，然后在每个频道内按测速分数排序
            def sort_channel_sources(group):
                if self.config["enable_ffmpeg_test"] and 'speed_score' in group.columns:
                    return group.sort_values('speed_score', ascending=False)
                return group
            
            sorted_df = filtered_df.groupby('template_channel', group_keys=False).apply(sort_channel_sources)
            
            # 限制每个频道最多源数量
            def limit_sources(group):
                return group.head(self.config["max_sources_per_channel"])
            
            result_df = sorted_df.groupby('template_channel', group_keys=False).apply(limit_sources)
            result_df = result_df.sort_values('channel_order')
            
            # 清理临时列
            if 'channel_order' in result_df.columns:
                result_df = result_df.drop('channel_order', axis=1)
            
            print(f"最终保留: {len(result_df)} 个流")
            return result_df
            
        except Exception as e:
            print(f"过滤和排序频道时出错: {e}")
            return pd.DataFrame()

    def save_to_txt(self, df: pd.DataFrame):
        """保存为TXT格式，严格按照模板结构"""
        if df.empty:
            print("错误: 没有数据可以保存")
            return
            
        try:
            # 按模板频道组织数据
            channels_data = {}
            for _, row in df.iterrows():
                template_channel = row.get('template_channel', '')
                url = row.get('stream_url', '')
                
                if not template_channel or not url:
                    continue
                    
                score = row.get('speed_score', 0)
                
                if template_channel not in channels_data:
                    channels_data[template_channel] = []
                
                channels_data[template_channel].append((url, score))
            
            with open(self.output_txt, 'w', encoding='utf-8') as f:
                f.write("# 生成时间: {}\n".format(pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')))
                f.write("# 总频道数: {}\n".format(len(channels_data)))
                f.write("# 总流数: {}\n".format(len(df))))
                if self.config["enable_ffmpeg_test"]:
                    f.write("# FFmpeg测速: 速度权重{} 响应权重{}\n".format(
                        self.config["speed_weight"], self.config["response_weight"]))
                f.write("# 频道名称智能匹配，每个频道最多{}个IPv4源\n\n".format(self.config["max_sources_per_channel"]))
                
                # 按照模板结构写入
                current_genre = ""
                for item in self.template_structure:
                    if item['type'] == 'genre':
                        # 写入分类标题
                        f.write(f"{item['name']},#genre#\n")
                        current_genre = item['name']
                    elif item['type'] == 'channel':
                        template_channel = item['name']
                        # 写入该频道的所有源
                        if template_channel in channels_data and channels_data[template_channel]:
                            for url, score in channels_data[template_channel]:
                                if self.config["enable_ffmpeg_test"]:
                                    f.write(f"{template_channel},{url}#score={score:.3f}\n")
                                else:
                                    f.write(f"{template_channel},{url}\n")
            
            print(f"TXT文件已保存: {os.path.abspath(self.output_txt)}")
            
        except Exception as e:
            print(f"保存TXT文件时出错: {e}")

    def save_to_m3u(self, df: pd.DataFrame):
        """保存为M3U格式，严格按照模板结构"""
        if df.empty:
            print("错误: 没有数据可以保存")
            return
            
        try:
            # 按模板频道组织数据
            channels_data = {}
            for _, row in df.iterrows():
                template_channel = row.get('template_channel', '')
                url = row.get('stream_url', '')
                
                if not template_channel or not url:
                    continue
                    
                score = row.get('speed_score', 0)
                
                if template_channel not in channels_data:
                    channels_data[template_channel] = []
                
                channels_data[template_channel].append((url, score))
            
            with open(self.output_m3u, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                f.write("# Generated: {}\n".format(pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')))
                f.write("# Total Channels: {}\n".format(len(channels_data)))
                f.write("# Total Streams: {}\n".format(len(df)))
                if self.config["enable_ffmpeg_test"]:
                    f.write("# FFmpeg Test: speed_weight={} response_weight={}\n".format(
                        self.config["speed_weight"], self.config["response_weight"]))
                f.write("# Smart channel matching, max {} IPv4 sources per channel\n".format(self.config["max_sources_per_channel"]))
                
                # 按照模板结构写入
                for item in self.template_structure:
                    if item['type'] == 'channel':
                        template_channel = item['name']
                        # 写入该频道的所有源
                        if template_channel in channels_data and channels_data[template_channel]:
                            for url, score in channels_data[template_channel]:
                                if self.config["enable_ffmpeg_test"]:
                                    f.write(f'#EXTINF:-1 tvg-name="{template_channel}" tvg-logo="" group-title="{item["genre"]}",{template_channel} [Score:{score:.3f}]\n')
                                else:
                                    f.write(f'#EXTINF:-1 tvg-name="{template_channel}" tvg-logo="" group-title="{item["genre"]}",{template_channel}\n')
                                f.write(f'{url}\n')
            
            print(f"M3U文件已保存: {os.path.abspath(self.output_m3u)}")
            
        except Exception as e:
            print(f"保存M3U文件时出错: {e}")

    def run(self):
        """运行爬虫"""
        print("开始抓取IPTV直播源...")
        print("=" * 50)
        
        # 检查模板文件
        if not self.template_structure:
            print("错误: 没有找到模板结构，请创建 demo.txt 文件")
            return
        
        try:
            # 获取在线源数据
            online_content = self.fetch_all_streams()
            
            # 整理所有源数据
            print("整理源数据中...")
            all_streams_df = self.organize_streams(online_content)
            
            if not all_streams_df.empty:
                # 过滤和排序
                print("按照模板过滤和排序...")
                filtered_df = self.filter_and_sort_channels(all_streams_df)
                
                if not filtered_df.empty:
                    # 保存文件
                    self.save_to_txt(filtered_df)
                    self.save_to_m3u(filtered_df)
                    print("=" * 50)
                    print("任务完成!")
                    
                    # 统计信息
                    channel_count = filtered_df['template_channel'].nunique()
                    stream_count = len(filtered_df)
                    print(f"最终结果: {channel_count} 个频道, {stream_count} 个流")
                    
                    # 显示分类统计
                    if 'template_genre' in filtered_df.columns:
                        genre_stats = filtered_df.groupby('template_genre')['template_channel'].nunique()
                        print("\n分类统计:")
                        for genre, count in genre_stats.items():
                            print(f"  {genre}: {count} 个频道")
                    
                    # 显示测速统计
                    if self.config["enable_ffmpeg_test"] and 'speed_score' in filtered_df.columns:
                        avg_score = filtered_df['speed_score'].mean()
                        success_count = len([x for x in filtered_df.to_dict('records') if x.get('success', False)])
                        print(f"测速统计: 平均分数 {avg_score:.3f}, 成功测试 {success_count}/{stream_count}")
                else:
                    print("错误: 过滤后没有有效数据")
            else:
                print("错误: 没有获取到任何有效数据")
                
        except Exception as e:
            print(f"运行过程中出现错误: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    try:
        crawler = IPTVCrawler()
        crawler.run()
    except KeyboardInterrupt:
        print("\n用户中断程序")
    except Exception as e:
        print(f"程序运行出错: {e}")
        import traceback
        traceback.print_exc()
