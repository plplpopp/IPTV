#!/usr/bin/env python3
"""
增强版IPTV频道搜索工具 - 针对streaml.freetv.fun优化
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
            'fuzzy_match_threshold': 60,
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
            
            # 调试：保存原始内容用于分析
            with open('debug_content.txt', 'w', encoding='utf-8') as f:
                f.write(response.text)
            self.logger.info("原始内容已保存到 debug_content.txt")
            
            return response.text
            
        except requests.exceptions.Timeout:
            self.logger.error("请求超时")
        except requests.exceptions.ConnectionError:
            self.logger.error("连接错误")
        except Exception as e:
            self.logger.error(f"获取内容失败: {str(e)}")
        
        return None

    def extract_channels_optimized(self, content: str) -> List[Dict]:
        """针对streaml.freetv.fun优化的频道提取方法"""
        start_time = time.time()
        channels = []
        
        if not content:
            return channels
        
        self.logger.info("开始分析内容格式...")
        
        # 分析内容中的URL模式
        lines = content.splitlines()
        self.logger.info(f"内容共 {len(lines)} 行")
        
        # 调试：显示前几行内容
        for i, line in enumerate(lines[:10]):
            self.logger.debug(f"第{i+1}行: {line[:100]}...")
        
        # 针对streaml.freetv.fun的特定格式
        patterns = [
            # 格式: 频道名称,https://streaml.freetv.fun/xxxx
            (r'^([^,\r\n]+?)\s*,\s*(https?://streaml\.freetv\.fun/[^\s,\r\n]+)', 'streaml_freetv_format'),
            
            # 通用格式: 名称,URL
            (r'^([^,\r\n]+?)\s*,\s*(https?://[^\s,\r\n]+)', 'comma_separated'),
            
            # 格式: 名称 URL (空格分隔)
            (r'^([^,\r\n]+?)\s+(https?://[^\s]+)', 'space_separated'),
            
            # 包含CCTV或卫视关键词的行
            (r'([Cc][Cc][Tt][Vv][^,\r\n]*?|卫视[^,\r\n]*?)[^https]*(https?://[^\s]+)', 'cctv_keyword'),
        ]
        
        seen_channels: Set[str] = set()
        total_matches = 0
        
        for pattern, pattern_name in patterns:
            try:
                matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
                self.logger.info(f"模式 '{pattern_name}' 找到 {len(matches)} 个匹配")
                total_matches += len(matches)
                
                for match in matches:
                    if len(match) == 2:
                        name, url = match
                    else:
                        continue
                    
                    channel = self._process_channel_data(name, url)
                    if channel and self._is_valid_channel(channel):
                        channel_key = self._get_channel_key(channel)
                        if channel_key not in seen_channels:
                            seen_channels.add(channel_key)
                            channels.append(channel)
                            self.logger.debug(f"提取频道: {channel['name']} -> {channel['url']}")
                            
            except Exception as e:
                self.logger.warning(f"模式 '{pattern_name}' 处理失败: {e}")
                continue
        
        # 如果常规模式没有找到，尝试逐行分析
        if not channels:
            channels = self._line_by_line_analysis(lines)
        
        self.stats['total_channels_found'] = len(channels)
        self.stats['extraction_time'] = time.time() - start_time
        
        self.logger.info(f"频道提取完成: 找到 {len(channels)} 个频道, 总匹配数: {total_matches}, 耗时: {self.stats['extraction_time']:.2f}s")
        return channels

    def _line_by_line_analysis(self, lines: List[str]) -> List[Dict]:
        """逐行分析内容"""
        channels = []
        seen_channels: Set[str] = set()
        
        self.logger.info("开始逐行分析内容...")
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or len(line) < 10:
                continue
                
            # 跳过明显的HTML标签
            if line.startswith('<') and line.endswith('>'):
                continue
                
            # 查找包含streaml.freetv.fun的行
            if 'streaml.freetv.fun' in line:
                # 尝试多种分割方式
                parts = line.split(',')
                if len(parts) >= 2:
                    # 最后一个部分应该是URL
                    url_candidate = parts[-1].strip()
                    name_candidate = ','.join(parts[:-1]).strip()
                    
                    if url_candidate.startswith('http') and name_candidate:
                        channel = self._process_channel_data(name_candidate, url_candidate)
                        if channel and self._is_valid_channel(channel):
                            channel_key = self._get_channel_key(channel)
                            if channel_key not in seen_channels:
                                seen_channels.add(channel_key)
                                channels.append(channel)
                                self.logger.debug(f"行{line_num}: {channel['name']}")
                
                # 尝试空格分割
                else:
                    parts = line.split()
                    if len(parts) >= 2:
                        for i in range(len(parts) - 1):
                            if parts[i+1].startswith('http') and 'streaml.freetv.fun' in parts[i+1]:
                                name_candidate = ' '.join(parts[:i+1])
                                url_candidate = parts[i+1]
                                
                                channel = self._process_channel_data(name_candidate, url_candidate)
                                if channel and self._is_valid_channel(channel):
                                    channel_key = self._get_channel_key(channel)
                                    if channel_key not in seen_channels:
                                        seen_channels.add(channel_key)
                                        channels.append(channel)
                                        self.logger.debug(f"行{line_num}: {channel['name']}")
        
        return channels

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
        
        # 特别允许streaml.freetv.fun域名
        if 'streaml.freetv.fun' in url_lower:
            return True
        
        # 排除其他常见非视频URL
        non_video_domains = [
            'google', 'baidu', 'qq.com', 'github', 'localhost',
            'wikipedia', 'twitter', 'facebook'
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

    def test_channel_speed(self, channel: Dict) -> Dict:
        """测试频道速度和质量"""
        if not self.config['enable_speed_test']:
            channel['score'] = 0.5
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
                
                if response_time > self.config['max_response_time']:
                    response_time = self.config['max_response_time']
                
                channel['response_time'] = response_time
                channel['content_type'] = response.headers.get('Content-Type', '')
                
                resolution_score = self._resolution_to_score(channel['resolution'])
                speed_score = 1 - (response_time / self.config['max_response_time'])
                
                channel['score'] = (
                    self.config['response_time_weight'] * speed_score +
                    self.config['resolution_weight'] * resolution_score +
                    self.config['bitrate_weight'] * 0.5
                )
                
            else:
                channel['response_time'] = float('inf')
                channel['score'] = 0
                
        except Exception as e:
            channel['response_time'] = float('inf')
            channel['score'] = 0
            
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
                match_score = max(
                    fuzz.token_set_ratio(template, channel['name']),
                    fuzz.partial_ratio(template, channel['name']),
                    fuzz.ratio(template, channel['name'])
                )
                
                if match_score >= self.config['fuzzy_match_threshold']:
                    channel['match_score'] = match_score
                    matched.append(channel)
            
            if matched:
                matched.sort(key=lambda x: (-x['match_score'], -x['score']))
                matched_channels[template] = matched[:self.config['zb_urls_limit']]
                self.logger.info(f"频道 {template}: 匹配到 {len(matched_channels[template])} 个源")
        
        self.stats['matched_channels'] = sum(len(v) for v in matched_channels.values())
        return matched_channels

    def _simple_channel_match(self, all_channels: List[Dict]) -> Dict[str, List[Dict]]:
        """简单频道匹配"""
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
        
        self.stats = {key: 0 for key in self.stats}
        
        content = self.fetch_content()
        if not content:
            self.logger.error("无法获取IPTV源内容")
            return {}
        
        all_channels = self.extract_channels_optimized(content)
        if not all_channels:
            self.logger.error("未提取到任何频道数据")
            return {}
        
        if self.config['enable_speed_test']:
            tested_channels = self.test_channels_speed(all_channels)
        else:
            tested_channels = all_channels
        
        matched_channels = self.match_template_channels(tested_channels)
        
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
                f.write('#EXTM3U\n')
                for template, channels in channels_dict.items():
                    for channel in channels:
                        f.write(f"#EXTINF:-1,{channel['name']}\n")
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
                            f.write(f"   地址: {channel['url']}\n\n")
            
            self.logger.info(f"文本文件保存成功: {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"保存文本文件失败: {e}")
            return False

    def run_complete_search(self, output_formats: List[str] = None):
        """运行完整搜索流程"""
        if output_formats is None:
            output_formats = ['m3u', 'txt']
        
        print("开始完整IPTV频道搜索...")
        print(f"目标源: {self.base_url}")
        print(f"输出格式: {', '.join(output_formats)}")
        print("-" * 50)
        
        channels_dict = self.search_channels()
        
        if not channels_dict:
            print("搜索完成，但未找到匹配的频道。")
            return False
        
        success_count = 0
        if 'm3u' in output_formats:
            if self.save_channels_to_m3u(channels_dict):
                success_count += 1
        if 'txt' in output_formats:
            if self.save_channels_to_txt(channels_dict):
                success_count += 1
        
        print(f"\n搜索完成！成功保存 {success_count} 个输出文件。")
        return True


def main():
    """主函数"""
    iptv_source = "http://188.68.248.8:55501/"
    
    searcher = AdvancedIPTVSearcher(iptv_source)
    
    # 调整配置以适应streaml.freetv.fun
    searcher.config.update({
        'zb_urls_limit': 8,
        'fuzzy_match_threshold': 50,  # 降低匹配阈值
        'max_concurrent_tasks': 10,
        'enable_speed_test': True,    # 可以设为False来加快速度
    })
    
    success = searcher.run_complete_search(['m3u', 'txt'])
    
    if success:
        print("\n使用说明:")
        print("1. M3U文件可用于VLC、PotPlayer等播放器")
        print("2. 文本文件包含详细的频道信息")
    else:
        print("\n搜索失败，请检查网络连接和源地址。")


if __name__ == "__main__":
    main()
