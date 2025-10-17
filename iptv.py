import requests
import re
import json
import time
import logging
import concurrent.futures
from fuzzywuzzy import fuzz
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse
import ssl
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class IPTVSearcher:
    def __init__(self, base_url: str = "http://188.68.248.8:55501/"):
        self.base_url = base_url
        self.session = self._create_session()
        
        # 增强的配置参数
        self.config = {
            'response_time_weight': 0.5,
            'resolution_weight': 0.5,
            'zb_urls_limit': 8,
            'max_concurrent_tasks': 10,
            'open_sort': True,
            'fuzzy_match_threshold': 70,
            'timeout': 15,
            'max_retries': 3,
            'retry_backoff': 0.5
        }
        
        self._setup_logging()
        self.template_channels = self._load_template_channels()
        
    def _create_session(self) -> requests.Session:
        """创建配置好的会话"""
        session = requests.Session()
        
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
