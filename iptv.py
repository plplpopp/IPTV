#!/usr/bin/env python3
"""
增强版IPTV频道搜索工具 - 完整优化版本
支持多种IPTV源格式，自动检测和调试
"""

import requests
import re
import json
import time
import logging
import concurrent.futures
from fuzzywuzzy import fuzz
from typing import List, Dict, Optional, Set, Tuple
import urllib3
import sys
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class AdvancedIPTVSearcher:
    def __init__(self, base_url: str = "http://188.68.248.8:55501/"):
        self.base_url = base_url
        self.session = self._create_robust_session()
        self._setup_logging()
        self._load_config()
        self.template_channels = self._load_template_channels()
        
        # 统计信息
        self.stats = {
            'total_channels_found': 0,
            'valid_channels_tested': 0,
            'matched_channels': 0,
            'extraction_time': 0,
            'testing_time': 0
        }

    def _create_robust_session(self) -> requests.Session:
        """创建健壮的会话连接"""
        session = requests.Session()
        
        # 重试策略
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=20
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache'
        })
        
        return session

    def _setup_logging(self):
        """配置日志系统"""
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            # 控制台处理器
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            
            # 文件处理器
            file_handler = logging.FileHandler('iptv_search.log', encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            
            # 格式化器
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)
            file_handler.setFormatter(formatter)
            
            logger.addHandler(console_handler)
            logger.addHandler(file_handler)
        
        self.logger = logging.getLogger(__name__)

    def _load_config(self):
        """加载配置参数"""
        self.config = {
            # 权重配置
            'response_time_weight': 0.6,
            'resolution_weight': 0.3,
            'bitrate_weight': 0.1,
            
            # 限制配置
            'zb_urls_limit': 10,
            'max_concurrent_tasks': 15,
            'max_channels_to_test': 200,
            
            # 匹配配置
            'fuzzy_match_threshold': 65,
            'min_channel_name_length': 2,
            'max_channel_name_length': 100,
            
            # 超时配置
            'request_timeout': 20,
            'speed_test_timeout': 8,
            'max_response_time': 10.0,
            
            # 功能开关
            'enable_speed_test': True,
            'enable_resolution_detection': True,
            'enable_fuzzy_matching': True,
            'remove_duplicates': True
        }

    def _load_template_channels(self) -> List[str]:
        """加载频道模板"""
        return [
            # CCTV系列
            "CCTV1", "CCTV2", "CCTV3", "CCTV4", "CCTV5", "CCTV5+", "CCTV6", "CCTV7", 
            "CCTV8", "CCTV9", "CCTV10", "CCTV11", "CCTV12", "CCTV13", "CCTV14", "CCTV15",
            "CCTV16", "CCTV17",
            
            # 卫视系列
            "北京卫视", "湖南卫视", "浙江卫视", "江苏卫视", "东方卫视", "安徽卫视",
            "山东卫视", "天津卫视", "湖北卫视", "广东卫视", "深圳卫视", "黑龙江卫视",
            "辽宁卫视", "四川卫视", "河南卫视", "东南卫视", "重庆卫视",
            
            # 其他重要频道
            "北京冬奥纪实", "中国教育1", "中国教育2", "金鹰卡通", "卡酷少儿",
            "嘉佳卡通", "优漫卡通", "炫动卡通"
        ]

    def analyze_content_format(self, content: str) -> Dict:
        """分析内容格式并返回最佳提取策略"""
        analysis = {
            'format_type': 'unknown',
            'total_lines': len(content.splitlines()),
            'content_length': len(content),
            'url_count': len(re.findall(r'https?://[^\s<>"\'{}|\\^`\[\]]+', content)),
            'm3u_style': False,
            'json_style': False,
            'csv_style': False,
            'recommended_patterns': []
        }
        
        # 检测M3U格式
        if '#EXTM3U' in content.upper():
            analysis['format_type'] = 'm3u'
            analysis['m3u_style'] = True
            analysis['recommended_patterns'].append('m3u_standard')
        
        # 检测JSON格式
        if content.strip().startswith('{') or content.strip().startswith('['):
            analysis['format_type'] = 'json'
            analysis['json_style'] = True
            analysis['recommended_patterns'].append('json_format')
        
        # 检测CSV格式
        lines = content.splitlines()
        if lines and ',' in lines[0] and any('http' in line for line in lines[:10]):
            analysis['format_type'] = 'csv'
            analysis['csv_style'] = True
            analysis['recommended_patterns'].append('csv_format')
        
        # 如果没有明确格式，尝试自动检测
        if analysis['format_type'] == 'unknown':
            if analysis['url_count'] > 0:
                analysis['format_type'] = 'mixed'
                analysis['recommended_patterns'].extend(['url_only', 'name_url_pairs'])
        
        return analysis

    def fetch_content(self) -> Optional[str]:
        """获取页面内容"""
        self.logger.info(f"开始获取IPTV源: {self.base_url}")
        
        try:
            start_time = time.time()
            response = self.session.get(
                self.base_url,
                timeout=self.config['request_timeout'],
                verify=False,
                allow_redirects=True
            )
            
            if response.status_code != 200:
                self.logger.error(f"HTTP错误: {response.status_code}")
                return None
            
            # 自动检测编码
            if response.encoding is None or response.encoding.lower() == 'iso-8859-1':
                response.encoding = response.apparent_encoding or 'utf-8'
            
            fetch_time = time.time() - start_time
            self.logger.info(f"成功获取内容: {len(response.text)} 字符, 耗时: {fetch_time:.2f}s")
            
            return response.text
            
        except requests.exceptions.Timeout:
            self.logger.error("请求超时")
        except requests.exceptions.ConnectionError:
            self.logger.error("连接错误")
        except Exception as e:
            self.logger.error(f"获取内容失败: {str(e)}")
        
        return None

    def extract_channels_advanced(self, content: str) -> List[Dict]:
        """高级频道提取方法"""
        start_time = time.time()
        channels = []
        
        if not content:
            return channels
        
        # 分析内容格式
        analysis = self.analyze_content_format(content)
        self.logger.info(f"内容格式分析: {analysis['format_type']}")
        
        # 根据分析结果选择提取模式
        extraction_patterns = self._get_extraction_patterns(analysis)
        
        seen_channels: Set[str] = set()
        
        for pattern_name, pattern in extraction_patterns:
            try:
                matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
                self.logger.debug(f"模式 '{pattern_name}' 找到 {len(matches)} 个匹配")
                
                for match in matches:
                    if len(match) == 2:
                        name, url = match
                    else:
                        # 处理单URL模式
                        url = match[0] if match else None
                        name = self._generate_channel_name(url)
                    
                    if name and url:
                        channel = self._process_channel_data(name, url)
                        if channel and self._is_valid_channel(channel):
                            channel_key = self._get_channel_key(channel)
                            if channel_key not in seen_channels:
                                seen_channels.add(channel_key)
                                channels.append(channel)
                                
            except Exception as e:
                self.logger.warning(f"模式 '{pattern_name}' 处理失败: {e}")
                continue
        
        # 如果没有找到频道，使用备选方法
        if not channels:
            channels = self._extract_fallback_channels(content)
        
        self.stats['total_channels_found'] = len(channels)
        self.stats['extraction_time'] = time.time() - start_time
        
        self.logger.info(f"频道提取完成: 找到 {len(channels)} 个频道, 耗时: {self.stats['extraction_time']:.2f}s")
        return channels

    def _get_extraction_patterns(self, analysis: Dict) -> List[Tuple[str, str]]:
        """根据分析结果获取提取模式"""
        patterns = []
        
        # M3U格式模式
        patterns.extend([
            ('m3u_standard', r'#EXTINF:.*?,(.+?)\s*\n\s*(https?://[^\s]+)'),
            ('m3u_simple', r'#EXTINF:.*?,(.+?)\s*[\r\n]+\s*(https?://[^\s]+)'),
        ])
        
        # 通用格式模式
        patterns.extend([
            ('name_url_comma', r'([^,\r\n]+?)\s*,\s*(https?://[^\s,\r\n]+)'),
            ('name_url_space', r'([^,\r\n]+?)\s+(https?://[^\s]+)'),
            ('quoted_pairs', r'["\']([^"\']+?)["\']\s*[,\|]\s*["\'](https?://[^"\']+)["\']'),
        ])
        
        # JSON格式模式
        patterns.extend([
            ('json_name_url', r'"name"\s*:\s*"([^"]+)"[^}]*"url"\s*:\s*"([^"]+)"'),
            ('json_title_url', r'"title"\s*:\s*"([^"]+)"[^}]*"url"\s*:\s*"([^"]+)"'),
        ])
        
        # URL-only模式（最后尝试）
        patterns.extend([
            ('url_only_name', r'([Cc][Cc][Tt][Vv][^,\r\n]*?|卫视[^,\r\n]*?)[^https]*(https?://[^\s]+)'),
            ('url_only', r'(https?://[^\s<>"\'{}|\\^`\[\]]+)'),
        ])
        
        return patterns

    def _process_channel_data(self, name: str, url: str) -> Dict:
        """处理频道数据"""
        clean_name = self._clean_channel_name(name)
        clean_url = self._clean_channel_url(url)
        
        return {
            'name': clean_name,
            'url': clean_url,
            'resolution': self._detect_resolution(clean_name),
            'bitrate': self._detect_bitrate(clean_name),
            'response_time': None,
            'score': 0,
            'match_score': 0,
            'content_type': None,
            'is_live': self._detect_live_stream(clean_name, clean_url)
        }

    def _clean_channel_name(self, name: str) -> str:
        """清理频道名称"""
        if not name or name.strip() == '':
            return "Unknown_Channel"
        
        # 移除特殊字符和多余空格
        name = re.sub(r'^[#\s\-_]*', '', name)
        name = re.sub(r'[\s\r\n\-_]+', ' ', name)
        
        # 移除常见无用后缀
        name = re.sub(r'\s*[\[\(].*?[\]\)]', '', name)
        name = re.sub(r'\s*(直播|Live|LIVE|HD|hd|FHD|4K|.*p|超清|高清|标清|流畅)$', '', name)
        
        # 限制长度
        name = name.strip()
        if len(name) < self.config['min_channel_name_length']:
            name = f"Channel_{hash(name) % 10000:04d}"
        elif len(name) > self.config['max_channel_name_length']:
            name = name[:self.config['max_channel_name_length']]
        
        return name

    def _clean_channel_url(self, url: str) -> str:
        """清理URL"""
        url = url.strip()
        # 移除URL中的多余空格和换行符
        url = re.sub(r'[\s\r\n]+', '', url)
        return url

    def _generate_channel_name(self, url: str) -> str:
        """根据URL生成频道名称"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '')
            return f"Channel_{domain}"
        except:
            return f"Channel_{hash(url) % 10000:04d}"

    def _is_valid_channel(self, channel: Dict) -> bool:
        """验证频道有效性"""
        name = channel['name']
        url = channel['url']
        
        if not name or not url:
            return False
        
        # 排除无效关键词
        invalid_keywords = [
            'example', 'test', 'demo', '样本', '测试', '备用', 
            '#EXT', 'localhost', '127.0.0.1', '::1'
        ]
        
        name_lower = name.lower()
        url_lower = url.lower()
        
        if any(kw in name_lower for kw in invalid_keywords):
            return False
        
        if any(kw in url_lower for kw in invalid_keywords):
            return False
        
        # 检查URL格式
        if not url.startswith(('http://', 'https://')):
            return False
        
        # 排除常见非视频URL
        non_video_domains = [
            'google', 'baidu', 'qq.com', 'github', 'localhost',
            'wikipedia', 'twitter', 'facebook', 'youtube.com'
        ]
        
        if any(domain in url_lower for domain in non_video_domains):
            return False
        
        return True

    def _get_channel_key(self, channel: Dict) -> str:
        """获取频道唯一标识"""
        return f"{channel['name'].lower()}|{channel['url']}"

    def _detect_resolution(self, name: str) -> str:
        """检测分辨率"""
        if not self.config['enable_resolution_detection']:
            return '未知'
            
        text = name.lower()
        resolution_patterns = [
            ('3840x2160', r'3840x2160|4k|2160p|超高清'),
            ('1920x1080', r'1920x1080|1080p|1080|高清|hd|high.definition'),
            ('1280x720', r'1280x720|720p|720'),
            ('1024x576', r'1024x576|576p|576'),
            ('720x576', r'720x576'),
            ('720x480', r'720x480'),
            ('标清', r'标清|sd|480p|360p|流畅')
        ]
        
        for res, pattern in resolution_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return res
        return '未知'

    def _detect_bitrate(self, name: str) -> Optional[str]:
        """检测码率"""
        bitrate_match = re.search(r'(\d+)\s*(kbps|mbps|k|m)', name.lower())
        if bitrate_match:
            return bitrate_match.group(0)
        return None

    def _detect_live_stream(self, name: str, url: str) -> bool:
        """检测是否为直播流"""
        live_indicators = ['live', '直播', 'rtmp', 'rtsp', 'mms', 'udp']
        text = f"{name} {url}".lower()
        return any(indicator in text for indicator in live_indicators)

    def _extract_fallback_channels(self, content: str) -> List[Dict]:
        """备选频道提取方法"""
        channels = []
        url_pattern = r'(https?://[^\s<>"\'{}|\\^`\[\]]+)'
        urls = re.findall(url_pattern, content)
        
        self.logger.info(f"使用备选方法提取URL: 找到 {len(urls)} 个URL")
        
        # 限制处理数量
        urls = urls[:self.config['max_channels_to_test']]
        
        for i, url in enumerate(urls):
            channel_name = self._generate_channel_name(url)
            channel = self._process_channel_data(channel_name, url)
            if self._is_valid_channel(channel):
                channels.append(channel)
        
        return channels

    def test_channel_speed(self, channel: Dict) -> Dict:
        """测试频道速度和质量"""
        if not self.config['enable_speed_test']:
            channel['score'] = 0.5  # 默认分数
            return channel
            
        try:
            start_time = time.time()
            response = self.session.head(
                channel['url'],
                timeout=self.config['speed_test_timeout'],
                allow_redirects=True,
                verify=False
            )
            
            if response.status_code == 200:
                response_time = time.time() - start_time
                
                # 限制最大响应时间
                if response_time > self.config['max_response_time']:
                    response_time = self.config['max_response_time']
                
                channel['response_time'] = response_time
                channel['content_type'] = response.headers.get('Content-Type', '')
                
                # 计算综合评分
                resolution_score = self._resolution_to_score(channel['resolution'])
                speed_score = 1 - (response_time / self.config['max_response_time'])
                
                channel['score'] = (
                    self.config['response_time_weight'] * speed_score +
                    self.config['resolution_weight'] * resolution_score +
                    self.config['bitrate_weight'] * 0.5  # 默认码率分数
                )
                
                self.logger.debug(f"频道测试成功: {channel['name']} - 响应: {response_time:.2f}s - 评分: {channel['score']:.2f}")
                
            else:
                channel['response_time'] = float('inf')
                channel['score'] = 0
                
        except Exception as e:
            channel['response_time'] = float('inf')
            channel['score'] = 0
            self.logger.debug(f"频道测试失败: {channel['name']} - {e}")
            
        return channel

    def _resolution_to_score(self, resolution: str) -> float:
        """分辨率转分数"""
        scores = {
            '3840x2160': 1.0,
            '1920x1080': 0.8,
            '1280x720': 0.6,
            '1024x576': 0.5,
            '720x576': 0.4,
            '720x480': 0.3,
            '标清': 0.2,
            '未知': 0.1
        }
        return scores.get(resolution, 0.1)

    def test_channels_speed(self, channels: List[Dict]) -> List[Dict]:
        """并发测试频道速度"""
        if not channels:
            return []
            
        start_time = time.time()
        
        # 限制测试数量
        channels_to_test = channels[:self.config['max_channels_to_test']]
        self.logger.info(f"开始测试 {len(channels_to_test)} 个频道的速度...")
        
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.config['max_concurrent_tasks']
        ) as executor:
            futures = {
                executor.submit(self.test_channel_speed, channel): channel 
                for channel in channels_to_test
            }
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    channel = futures[future]
                    self.logger.error(f"频道测试异常 {channel['name']}: {e}")
        
        # 过滤无效频道并排序
        valid_channels = [c for c in channels_to_test if c['response_time'] != float('inf')]
        valid_channels.sort(key=lambda x: x['score'], reverse=True)
        
        self.stats['valid_channels_tested'] = len(valid_channels)
        self.stats['testing_time'] = time.time() - start_time
        
        self.logger.info(f"速度测试完成: 有效频道 {len(valid_channels)}/{len(channels_to_test)}, 耗时: {self.stats['testing_time']:.2f}s")
        return valid_channels

    def match_template_channels(self, all_channels: List[Dict]) -> Dict[str, List[Dict]]:
        """匹配模板频道"""
        if not self.config['enable_fuzzy_matching']:
            return self._simple_channel_match(all_channels)
            
        matched_channels = {}
        
        for template in self.template_channels:
            matched = []
            for channel in all_channels:
                # 使用多种匹配策略
                match_score = max(
                    fuzz.token_set_ratio(template, channel['name']),
                    fuzz.partial_ratio(template, channel['name']),
                    fuzz.ratio(template, channel['name'])
                )
                
                if match_score >= self.config['fuzzy_match_threshold']:
                    channel['match_score'] = match_score
                    matched.append(channel)
            
            if matched:
                # 按匹配度和评分排序
                matched.sort(key=lambda x: (-x['match_score'], -x['score']))
                matched_channels[template] = matched[:self.config['zb_urls_limit']]
                self.logger.info(f"频道 {template}: 匹配到 {len(matched_channels[template])} 个源")
        
        self.stats['matched_channels'] = sum(len(v) for v in matched_channels.values())
        return matched_channels

    def _simple_channel_match(self, all_channels: List[Dict]) -> Dict[str, List[Dict]]:
        """简单频道匹配（不使用模糊匹配）"""
        matched_channels = {}
        
        for template in self.template_channels:
            matched = []
            for channel in all_channels:
                if template.lower() in channel['name'].lower():
                    channel['match_score'] = 100
                    matched.append(channel)
            
            if matched:
                matched.sort(key=lambda x: x['score'], reverse=True)
                matched_channels[template] = matched[:self.config['zb_urls_limit']]
        
        return matched_channels

    def search_channels(self) -> Dict[str, List[Dict]]:
        """主搜索方法"""
        self.logger.info("开始IPTV频道搜索流程...")
        
        # 重置统计信息
        self.stats = {key: 0 for key in self.stats}
        
        # 1. 获取内容
        content = self.fetch_content()
        if not content:
            self.logger.error("无法获取IPTV源内容")
            return {}
        
        # 2. 提取频道
        all_channels = self.extract_channels_advanced(content)
        if not all_channels:
            self.logger.error("未提取到任何频道数据")
            return {}
        
        # 3. 测试速度
        if self.config['enable_speed_test']:
            tested_channels = self.test_channels_speed(all_channels)
        else:
            tested_channels = all_channels
        
        # 4. 匹配模板
        matched_channels = self.match_template_channels(tested_channels)
        
        # 5. 输出统计
        self._print_statistics(matched_channels)
        
        return matched_channels

    def _print_statistics(self, channels_dict: Dict[str, List[Dict]]):
        """打印统计信息"""
        total_matched = sum(len(v) for v in channels_dict.values())
        
        print("\n" + "="*50)
        print("IPTV频道搜索统计报告")
        print("="*50)
        print(f"总发现频道: {self.stats['total_channels_found']}")
        print(f"有效测试频道: {self.stats['valid_channels_tested']}")
        print(f"匹配模板频道: {self.stats['matched_channels']}")
        print(f"最终频道组数: {len(channels_dict)}")
        print(f"最终频道源数: {total_matched}")
        print(f"提取耗时: {self.stats['extraction_time']:.2f}s")
        print(f"测试耗时: {self.stats['testing_time']:.2f}s")
        print(f"总耗时: {self.stats['extraction_time'] + self.stats['testing_time']:.2f}s")
        
        # 分辨率统计
        if channels_dict:
            resolutions = {}
            for channels in channels_dict.values():
                for channel in channels:
                    res = channel['resolution']
                    resolutions[res] = resolutions.get(res, 0) + 1
            
            print("\n分辨率分布:")
            for res, count in sorted(resolutions.items(), key=lambda x: x[1], reverse=True):
                print(f"  {res}: {count}个")

    def save_channels_to_m3u(self, channels_dict: Dict[str, List[Dict]], filename: str = "iptv_channels.m3u"):
        """保存为M3U格式"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U x-tvg-url=""\n')
                for template, channels in channels_dict.items():
                    for channel in channels:
                        # 构建EXTINF行
                        extinf_line = f"#EXTINF:-1 tvg-name=\"{channel['name']}\""
                        if channel['resolution'] != '未知':
                            extinf_line += f" tvg-resolution=\"{channel['resolution']}\""
                        if channel['response_time']:
                            extinf_line += f" response-time=\"{channel['response_time']:.2f}\""
                        extinf_line += f",{channel['name']}\n"
                        
                        f.write(extinf_line)
                        f.write(f"{channel['url']}\n")
            
            self.logger.info(f"M3U文件保存成功: {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"保存M3U文件失败: {e}")
            return False

    def save_channels_to_txt(self, channels_dict: Dict[str, List[Dict]], filename: str = "iptv_channels.txt"):
        """保存为文本格式"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("IPTV频道列表\n")
                f.write("=" * 50 + "\n\n")
                
                for template in self.template_channels:
                    if template in channels_dict and channels_dict[template]:
                        f.write(f"【{template}】\n")
                        f.write("-" * 30 + "\n")
                        
                        for i, channel in enumerate(channels_dict[template], 1):
                            f.write(f"{i}. {channel['name']}\n")
                            f.write(f"   分辨率: {channel['resolution']}\n")
                            if channel['response_time']:
                                f.write(f"   响应时间: {channel['response_time']:.2f}s\n")
                            f.write(f"   综合评分: {channel['score']:.2f}\n")
                            if channel['match_score']:
                                f.write(f"   匹配度: {channel['match_score']}%\n")
                            f.write(f"   地址: {channel['url']}\n\n")
            
            self.logger.info(f"文本文件保存成功: {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"保存文本文件失败: {e}")
            return False

    def save_channels_to_json(self, channels_dict: Dict[str, List[Dict]], filename: str = "iptv_channels.json"):
        """保存为JSON格式"""
        try:
            # 准备JSON数据
            output_data = {
                "metadata": {
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "source_url": self.base_url,
                    "total_groups": len(channels_dict),
                    "total_channels": sum(len(v) for v in channels_dict.values())
                },
                "channels": channels_dict
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"JSON文件保存成功: {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"保存JSON文件失败: {e}")
            return False

    def run_complete_search(self, output_formats: List[str] = None):
        """运行完整搜索流程"""
        if output_formats is None:
            output_formats = ['m3u', 'txt', 'json']
        
        print("开始完整IPTV频道搜索...")
        print(f"目标源: {self.base_url}")
        print(f"输出格式: {', '.join(output_formats)}")
        print("-" * 50)
        
        # 执行搜索
        channels_dict = self.search_channels()
        
        if not channels_dict:
            print("搜索完成，但未找到匹配的频道。")
            return False
        
        # 保存结果
        success_count = 0
        if 'm3u' in output_formats:
            if self.save_channels_to_m3u(channels_dict):
                success_count += 1
        if 'txt' in output_formats:
            if self.save_channels_to_txt(channels_dict):
                success_count += 1
        if 'json' in output_formats:
            if self.save_channels_to_json(channels_dict):
                success_count += 1
        
        print(f"\n搜索完成！成功保存 {success_count} 个输出文件。")
        return True


def main():
    """主函数"""
    # 可以在这里修改IPTV源地址
    iptv_source = "http://188.68.248.8:55501/"
    
    # 创建搜索器实例
    searcher = AdvancedIPTVSearcher(iptv_source)
    
    # 可选：调整配置
    searcher.config.update({
        'zb_urls_limit': 8,
        'fuzzy_match_threshold': 60,
        'max_concurrent_tasks': 20,
    })
    
    # 运行完整搜索
    success = searcher.run_complete_search(['m3u', 'txt', 'json'])
    
    if success:
        print("\n使用说明:")
        print("1. M3U文件可用于VLC、PotPlayer等播放器")
        print("2. 文本文件包含详细的频道信息")
        print("3. JSON文件可用于程序处理")
    else:
        print("\n搜索失败，请检查网络连接和源地址。")


if __name__ == "__main__":
    main()        session = requests.Session()
        
        # 重试策略
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive'
        })
        
        return session

    def _setup_logging(self):
        """配置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('iptv_search.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _load_template_channels(self) -> List[str]:
        """加载频道模板"""
        return [
            "CCTV1综合", "CCTV2财经", "CCTV3综艺", "CCTV4国际", 
            "CCTV5体育", "CCTV6电影", "CCTV7军事", "CCTV8电视剧",
            "CCTV9纪录", "CCTV10科教", "CCTV11戏曲", "CCTV12社会与法",
            "CCTV13新闻", "CCTV14少儿", "CCTV15音乐", "CCTV16奥林匹克",
            "CCTV17农业农村", "CCTV5+体育赛事", "北京卫视", "湖南卫视",
            "浙江卫视", "江苏卫视", "东方卫视", "安徽卫视",
            "山东卫视", "天津卫视", "湖北卫视", "广东卫视",
            "深圳卫视", "黑龙江卫视", "辽宁卫视", "四川卫视"
        ]

    def fetch_page_content(self) -> Optional[str]:
        """获取页面内容 - 增强版本"""
        for attempt in range(self.config['max_retries']):
            try:
                response = self.session.get(
                    self.base_url, 
                    timeout=self.config['timeout'],
                    verify=False
                )
                response.raise_for_status()
                
                # 自动检测编码
                if response.encoding is None:
                    response.encoding = response.apparent_encoding
                
                self.logger.info(f"成功获取页面内容，长度: {len(response.text)}")
                return response.text
                
            except requests.exceptions.Timeout:
                self.logger.warning(f"请求超时 ({attempt+1}/{self.config['max_retries']})")
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"请求失败 ({attempt+1}/{self.config['max_retries']}): {e}")
            
            if attempt < self.config['max_retries'] - 1:
                time.sleep(self.config['retry_backoff'] * (2 ** attempt))
        
        return None

    def extract_channel_data(self, html_content: str) -> List[Dict]:
        """提取频道数据 - 增强版本"""
        channels = []
        if not html_content:
            return channels

        # 增强的正则模式
        patterns = [
            r'#EXTINF:.*?,(.+?)\s*\n\s*(https?://[^\s]+)',  # M3U格式
            r'([^,\r\n]+?)\s*,\s*(https?://[^\s,\r\n]+)',   # CSV格式
            r'["\']([^"\']+?)["\']\s*,\s*["\'](https?://[^"\']+)["\']',  # JSON-like
            r'channel.*?name\s*[:=]\s*["\']([^"\']+)["\'][^}]*?url\s*[:=]\s*["\'](https?://[^"\']+)["\']',  # 对象格式
        ]

        seen_channels = set()
        
        for pattern in patterns:
            matches = re.finditer(pattern, html_content, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                name, url = match.groups()
                clean_name = self.clean_channel_name(name)
                clean_url = self.clean_channel_url(url)
                
                if self.is_valid_channel(clean_name, clean_url):
                    channel_key = f"{clean_name.lower()}|{clean_url}"
                    if channel_key not in seen_channels:
                        seen_channels.add(channel_key)
                        channels.append({
                            'name': clean_name,
                            'url': clean_url,
                            'resolution': self.detect_resolution(clean_name),
                            'response_time': None,
                            'score': 0,
                            'match_score': 0,
                            'bitrate': self.detect_bitrate(clean_name)
                        })
        
        self.logger.info(f"从页面提取到 {len(channels)} 个频道")
        return channels

    def clean_channel_name(self, name: str) -> str:
        """清理频道名称"""
        # 移除多余符号和空格
        name = re.sub(r'^[#\s\-_]*', '', name)
        name = re.sub(r'[\s\r\n\-_]+', ' ', name)
        
        # 移除常见无用后缀
        name = re.sub(r'\s*[\[\(].*?[\]\)]', '', name)
        name = re.sub(r'\s*(直播|Live|LIVE|HD|hd|FHD|4K|.*p)$', '', name)
        
        return name.strip()

    def clean_channel_url(self, url: str) -> str:
        """清理URL"""
        url = url.strip()
        # 移除URL中的多余参数（可选）
        # parsed = urlparse(url)
        # clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        return url

    def is_valid_channel(self, name: str, url: str) -> bool:
        """验证频道有效性"""
        if not name or not url:
            return False
            
        invalid_keywords = ['example', 'test', 'demo', '样本', '测试', '备用']
        name_lower = name.lower()
        
        # 检查无效关键词
        if any(kw in name_lower for kw in invalid_keywords):
            return False
            
        # 检查URL格式
        if not url.startswith(('http://', 'https://')):
            return False
            
        # 检查名称长度
        if len(name) < 2 or len(name) > 100:
            return False
            
        return True

    def detect_resolution(self, name: str) -> str:
        """检测分辨率"""
        text = name.lower()
        resolution_patterns = [
            ('3840x2160', r'3840x2160|4k|2160p|超高清'),
            ('1920x1080', r'1920x1080|1080p|1080|高清|hd|high.definition'),
            ('1280x720', r'1280x720|720p|720'),
            ('标清', r'标清|sd|480p|360p')
        ]
        
        for res, pattern in resolution_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return res
        return '未知'

    def detect_bitrate(self, name: str) -> Optional[str]:
        """检测码率"""
        bitrate_match = re.search(r'(\d+)\s*(kbps|mbps|k|m)', name.lower())
        if bitrate_match:
            return bitrate_match.group(0)
        return None

    def resolution_to_score(self, resolution: str) -> float:
        """分辨率转分数"""
        scores = {
            '3840x2160': 1.0, 
            '1920x1080': 0.8, 
            '1280x720': 0.6, 
            '标清': 0.4, 
            '未知': 0.2
        }
        return scores.get(resolution, 0.2)

    def test_channel_speed(self, channel: Dict) -> Dict:
        """测试频道速度 - 增强版本"""
        try:
            start_time = time.time()
            response = self.session.head(
                channel['url'],
                timeout=10,
                allow_redirects=True,
                verify=False
            )
            
            if response.status_code == 200:
                response_time = time.time() - start_time
                channel['response_time'] = response_time
                
                # 计算综合评分
                resolution_score = self.resolution_to_score(channel['resolution'])
                speed_score = 1 - min(response_time, 5) / 5  # 响应时间得分
                
                channel['score'] = (
                    self.config['response_time_weight'] * speed_score + 
                    self.config['resolution_weight'] * resolution_score
                )
                
                # 记录HTTP头信息
                channel['content_type'] = response.headers.get('Content-Type', '')
                channel['content_length'] = response.headers.get('Content-Length', '')
                
        except Exception as e:
            self.logger.debug(f"频道测试失败 {channel['name']}: {e}")
            channel['response_time'] = float('inf')
            channel['score'] = 0
            
        return channel

    def test_channels_speed(self, channels: List[Dict]) -> List[Dict]:
        """并发测试频道速度"""
        self.logger.info(f"开始测试 {len(channels)} 个频道的速度...")
        
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.config['max_concurrent_tasks']
        ) as executor:
            future_to_channel = {
                executor.submit(self.test_channel_speed, channel): channel 
                for channel in channels
            }
            
            for future in concurrent.futures.as_completed(future_to_channel):
                try:
                    future.result()
                except Exception as e:
                    self.logger.error(f"频道测试异常: {e}")
        
        # 过滤无效频道并排序
        valid_channels = [c for c in channels if c['response_time'] != float('inf')]
        
        if self.config['open_sort']:
            valid_channels.sort(key=lambda x: x['score'], reverse=True)
            
        self.logger.info(f"速度测试完成，有效频道: {len(valid_channels)}")
        return valid_channels

    def match_template_channels(self, all_channels: List[Dict]) -> Dict[str, List[Dict]]:
        """匹配模板频道"""
        matched_channels = {}
        
        for template in self.template_channels:
            matched = []
            for channel in all_channels:
                match_score = fuzz.token_set_ratio(template, channel['name'])
                if match_score >= self.config['fuzzy_match_threshold']:
                    channel['match_score'] = match_score
                    matched.append(channel)
            
            if matched:
                # 按匹配度和评分排序
                matched.sort(key=lambda x: (-x['match_score'], -x['score']))
                matched_channels[template] = matched[:self.config['zb_urls_limit']]
                self.logger.info(f"频道 {template} 匹配到 {len(matched_channels[template])} 个源")
        
        return matched_channels

    def search_channels_by_template(self) -> Dict[str, List[Dict]]:
        """主搜索方法"""
        self.logger.info("开始搜索IPTV频道...")
        
        html_content = self.fetch_page_content()
        if not html_content:
            self.logger.error("无法获取页面内容")
            return {}
        
        all_channels = self.extract_channel_data(html_content)
        if not all_channels:
            self.logger.error("未提取到频道数据")
            return {}
        
        tested_channels = self.test_channels_speed(all_channels)
        return self.match_template_channels(tested_channels)

    def save_channels_to_m3u(self, channels_dict: Dict[str, List[Dict]], filename: str = "iptv_channels.m3u"):
        """保存为M3U格式"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U x-tvg-url=""\n')
                for template in self.template_channels:
                    if template in channels_dict:
                        for channel in channels_dict[template]:
                            f.write(f"#EXTINF:-1 tvg-name=\"{channel['name']}\" tvg-logo=\"\",{channel['name']}\n")
                            f.write(f"{channel['url']}\n")
            self.logger.info(f"已保存M3U文件: {filename}")
        except Exception as e:
            self.logger.error(f"保存M3U失败: {e}")

    def save_channels_to_json(self, channels_dict: Dict[str, List[Dict]], filename: str = "iptv_channels.json"):
        """保存为JSON格式"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(channels_dict, f, ensure_ascii=False, indent=2)
            self.logger.info(f"已保存JSON文件: {filename}")
        except Exception as e:
            self.logger.error(f"保存JSON失败: {e}")

    def print_statistics(self, channels_dict: Dict[str, List[Dict]]):
        """打印统计信息"""
        total_channels = sum(len(v) for v in channels_dict.values())
        matched_templates = len(channels_dict)
        
        print(f"\n=== 搜索统计 ===")
        print(f"匹配的频道组: {matched_templates}/{len(self.template_channels)}")
        print(f"总频道源数: {total_channels}")
        
        # 分辨率统计
        resolutions = {}
        for channels in channels_dict.values():
            for channel in channels:
                res = channel['resolution']
                resolutions[res] = resolutions.get(res, 0) + 1
        
        print(f"\n分辨率分布:")
        for res, count in resolutions.items():
            print(f"  {res}: {count}个")

def main():
    """主函数"""
    searcher = IPTVSearcher()
    
    print("开始搜索IPTV频道...")
    channels_dict = searcher.search_channels_by_template()
    
    if channels_dict:
        searcher.print_statistics(channels_dict)
        
        # 保存多种格式
        searcher.save_channels_to_m3u(channels_dict)
        searcher.save_channels_to_txt(channels_dict)
        searcher.save_channels_to_json(channels_dict)
        
        print("\n结果已保存到文件:")
        print("- iptv_channels.m3u (播放列表)")
        print("- iptv_channels.txt (文本格式)") 
        print("- iptv_channels.json (JSON格式)")
    else:
        print("未找到匹配的频道")

if __name__ == "__main__":
    main()
