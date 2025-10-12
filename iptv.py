import requests
import pandas as pd
import re
import os
import time
import concurrent.futures
import json
import hashlib
import pickle
import logging
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Set
from urllib.parse import urlparse
from tenacity import retry, stop_after_attempt, wait_exponential


class Config:
    """配置管理类"""
    DEFAULT_CONFIG = {
        'timeout': 10,
        'max_workers': 15,
        'test_size_kb': 512,  # 增大测试数据量以获得更准确的速度
        'cache_ttl_hours': 2,
        'max_sources_per_channel': 25,
        'keep_best_sources': 5,
        'min_speed_mbps': 0.3,  # 最低速度要求 0.3 MB/s
        'sources': [
            "https://raw.githubusercontent.com/zwc456baby/iptv_alive/master/live.txt",
            "https://live.zbds.top/tv/iptv6.txt", 
            "https://live.zbds.top/tv/iptv4.txt",
            "https://raw.githubusercontent.com/YanG-1989/m3u/main/Gather.m3u",
            "https://raw.githubusercontent.com/Free-IPTV/Countries/master/CN.m3u",
            "https://raw.githubusercontent.com/guaguagu/iptv/main/iptv.txt",
            "https://raw.githubusercontent.com/free-iptv/iptv/master/streams/cn.m3u",
            "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/cn.m3u",
        ],
        'output_formats': ['txt', 'm3u'],
        'template_file': 'demo.txt',
        'output_files': {
            'txt': 'iptv.txt',
            'm3u': 'iptv.m3u'
        }
    }
    
    def __init__(self, config_file='config.json'):
        self.config = self.DEFAULT_CONFIG.copy()
        self.config_file = config_file
        self.load_from_file()
    
    def load_from_file(self):
        """从文件加载配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    self.config.update(user_config)
                print(f"✅ 已加载配置文件: {self.config_file}")
            else:
                self.create_default_config()
        except Exception as e:
            print(f"❌ 加载配置文件失败: {str(e)}，使用默认配置")
    
    def create_default_config(self):
        """创建默认配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
            print(f"✅ 已创建默认配置文件: {self.config_file}")
        except Exception as e:
            print(f"❌ 创建配置文件失败: {str(e)}")
    
    def get(self, key, default=None):
        """获取配置值"""
        return self.config.get(key, default)


class CacheManager:
    """缓存管理"""
    def __init__(self, cache_dir='cache', ttl_hours=2):
        self.cache_dir = cache_dir
        self.ttl = timedelta(hours=ttl_hours)
        os.makedirs(cache_dir, exist_ok=True)
    
    def get_cache_key(self, url):
        """生成缓存键"""
        return hashlib.md5(url.encode()).hexdigest()[:16]
    
    def is_valid(self, cache_file):
        """检查缓存是否有效"""
        if not os.path.exists(cache_file):
            return False
        mod_time = datetime.fromtimestamp(os.path.getmtime(cache_file))
        return datetime.now() - mod_time < self.ttl
    
    def save(self, key, data):
        """保存缓存"""
        try:
            cache_file = os.path.join(self.cache_dir, f"{key}.pkl")
            with open(cache_file, 'wb') as f:
                pickle.dump({'data': data, 'timestamp': datetime.now()}, f)
        except Exception as e:
            print(f"缓存保存失败: {str(e)}")
    
    def load(self, key):
        """加载缓存"""
        try:
            cache_file = os.path.join(self.cache_dir, f"{key}.pkl")
            if self.is_valid(cache_file):
                with open(cache_file, 'rb') as f:
                    return pickle.load(f)['data']
        except Exception as e:
            print(f"缓存加载失败: {str(e)}")
        return None


class IPTV:
    """IPTV直播源抓取与测速工具"""
    
    def __init__(self, config_file='config.json'):
        """
        初始化工具
        
        Args:
            config_file: 配置文件路径
        """
        # 初始化配置
        self.config = Config(config_file)
        
        # 配置参数
        self.timeout = self.config.get('timeout', 10)
        self.max_workers = self.config.get('max_workers', 15)
        self.test_size = self.config.get('test_size_kb', 512) * 1024  # 转换为字节
        self.min_speed_mbps = self.config.get('min_speed_mbps', 0.3)
        
        # 初始化组件
        self.logger = self.setup_logging()
        self.cache_manager = CacheManager(ttl_hours=self.config.get('cache_ttl_hours', 2))
        
        # 请求会话配置
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Encoding': 'gzip, deflate',
            'Accept': '*/*',
            'Connection': 'keep-alive'
        })
        
        # 数据源配置
        self.source_urls = self.config.get('sources', [])
        
        # 正则表达式预编译
        self.ipv4_pattern = re.compile(r'^http://(\d{1,3}\.){3}\d{1,3}')
        self.ipv6_pattern = re.compile(r'^http://\[([a-fA-F0-9:]+)\]')
        self.channel_pattern = re.compile(r'^([^,#]+)')
        self.extinf_pattern = re.compile(r'#EXTINF:.*?,(.+)')
        
        # 文件路径配置
        self.template_file = self.config.get('template_file', 'demo.txt')
        output_files = self.config.get('output_files', {
            'txt': 'iptv.txt',
            'm3u': 'iptv.m3u'
        })
        self.output_files = {
            'txt': output_files['txt'],
            'm3u': output_files['m3u']
        }
        
        # 初始化状态
        self.template_channels = self.load_template_channels()
        self.all_streams = []

    def setup_logging(self, level=logging.INFO):
        """设置日志系统"""
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('iptv.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger(__name__)

    def load_template_channels(self) -> Set[str]:
        """加载模板文件中的频道列表"""
        channels = set()
        template_file = self.config.get('template_file', 'demo.txt')
        
        if not os.path.exists(template_file):
            self.logger.warning(f"模板文件 {template_file} 不存在，将处理所有频道")
            return channels
        
        try:
            with open(template_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if match := self.channel_pattern.match(line):
                            channel_name = self.normalize_channel_name(match.group(1).strip())
                            channels.add(channel_name)
            self.logger.info(f"加载模板频道 {len(channels)} 个")
        except Exception as e:
            self.logger.error(f"加载模板文件错误: {str(e)}")
        
        return channels

    def normalize_channel_name(self, name: str) -> str:
        """标准化频道名称"""
        # 去除多余空格和特殊字符
        name = re.sub(r'\s+', ' ', name.strip())
        
        # 统一央视命名
        cctv_patterns = [
            (r'CCTV-?(\d+)', r'CCTV\1'),
            (r'央视(\d+)', r'CCTV\1'),
            (r'中央(\d+)', r'CCTV\1')
        ]
        
        for pattern, replacement in cctv_patterns:
            name = re.sub(pattern, replacement, name)
        
        # 统一卫视频道命名
        ws_patterns = [
            (r'湖南卫视', '湖南卫视'),
            (r'江苏卫视', '江苏卫视'),
            (r'浙江卫视', '浙江卫视'),
            (r'东方卫视', '东方卫视'),
            (r'北京卫视', '北京卫视'),
        ]
        
        for pattern, replacement in ws_patterns:
            if pattern in name:
                name = replacement
                break
        
        return name

    # ==================== 数据获取与处理 ====================
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def fetch_with_retry(self, url):
        """带重试的抓取"""
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.text
        except Exception as e:
            self.logger.warning(f"抓取失败: {url}, 错误: {e}")
            raise

    def fetch_streams(self) -> Optional[str]:
        """从所有源URL抓取直播源"""
        contents = []
        successful_sources = 0
        
        for url in self.source_urls:
            domain = self._extract_domain(url)
            self.logger.info(f"抓取源: {domain}")
            
            # 检查缓存
            cache_key = self.cache_manager.get_cache_key(url)
            cached_content = self.cache_manager.load(cache_key)
            
            if cached_content:
                self.logger.info(f"  ✓ 使用缓存")
                contents.append(cached_content)
                successful_sources += 1
                continue
            
            try:
                content = self.fetch_with_retry(url)
                
                # 验证内容有效性
                if self.validate_content(content):
                    contents.append(content)
                    successful_sources += 1
                    self.cache_manager.save(cache_key, content)
                    self.logger.info(f"  ✓ 成功")
                else:
                    self.logger.warning(f"  ⚠️ 内容无效")
                    
            except Exception as e:
                self.logger.error(f"  ✗ 失败: {str(e)}")
        
        self.logger.info(f"成功抓取 {successful_sources}/{len(self.source_urls)} 个源")
        return "\n".join(contents) if contents else None

    def validate_content(self, content: str) -> bool:
        """验证内容是否为有效的直播源格式"""
        lines = content.splitlines()
        valid_lines = 0
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('http') or (',' in line and 'http' in line):
                valid_lines += 1
        
        return valid_lines >= 5

    def parse_content(self, content: str) -> pd.DataFrame:
        """解析直播源内容"""
        streams = []
        
        # 自动检测格式并解析
        if content.startswith("#EXTM3U"):
            streams.extend(self.parse_m3u_content(content))
        else:
            streams.extend(self.parse_txt_content(content))
        
        if not streams:
            self.logger.warning("未解析到有效直播源")
            return pd.DataFrame(columns=['program_name', 'stream_url'])
        
        df = pd.DataFrame(streams)
        
        # 数据清洗和标准化
        df = self.clean_stream_data(df)
        
        self.logger.info(f"解析到 {len(df)} 个直播源，{len(df['program_name'].unique())} 个频道")
        return df

    def parse_m3u_content(self, content: str) -> List[Dict]:
        """解析M3U格式内容"""
        streams = []
        current_program = None
        
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#EXTINF"):
                # 尝试多种格式提取节目名
                if match := re.search(r'tvg-name="([^"]+)"', line):
                    current_program = self.normalize_channel_name(match.group(1).strip())
                elif match := self.extinf_pattern.search(line):
                    current_program = self.normalize_channel_name(match.group(1).strip())
            elif line.startswith("http"):
                if current_program:
                    streams.append({
                        "program_name": current_program,
                        "stream_url": line
                    })
                current_program = None
        
        return streams

    def parse_txt_content(self, content: str) -> List[Dict]:
        """解析TXT格式内容"""
        streams = []
        
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            # 支持多种分隔符
            if ',' in line:
                parts = line.split(',', 1)
            elif ' ' in line and 'http' in line:
                parts = line.split(' ', 1)
            else:
                continue
                
            if len(parts) == 2:
                program_name = self.normalize_channel_name(parts[0].strip())
                stream_url = parts[1].strip()
                
                if program_name and stream_url.startswith('http'):
                    streams.append({
                        "program_name": program_name,
                        "stream_url": stream_url
                    })
        
        return streams

    def clean_stream_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """数据清洗"""
        if df.empty:
            return df
        
        # 去除节目名中的多余空格
        df['program_name'] = df['program_name'].str.strip()
        
        # 过滤无效URL
        initial_count = len(df)
        df = df[df['stream_url'].str.startswith('http')]
        
        # 去除明显无效的节目名
        invalid_names = ['', 'None', 'null', 'undefined']
        df = df[~df['program_name'].isin(invalid_names)]
        
        # 去除重复的节目名和URL组合
        df = df.drop_duplicates(subset=['program_name', 'stream_url'])
        
        self.logger.info(f"数据清洗: {initial_count} -> {len(df)} 个源")
        return df

    def organize_streams(self, df: pd.DataFrame) -> pd.DataFrame:
        """整理直播源数据，每个频道最多保留指定数量的源用于测速"""
        max_sources = self.config.get('max_sources_per_channel', 25)
        grouped = df.groupby('program_name')['stream_url'].apply(list).reset_index()
        
        # 限制每个频道的源数量
        grouped['stream_url'] = grouped['stream_url'].apply(lambda x: x[:max_sources])
        
        self.logger.info(f"整理后: {len(grouped)} 个频道，每个频道最多{max_sources}个源")
        return grouped

    # ==================== 增强测速功能 ====================
    
    def test_single_url(self, url: str) -> Tuple[Optional[float], Optional[str], float]:
        """
        测试单个URL的速度，返回速度(MB/s)、错误信息和响应时间
        
        Args:
            url: 要测试的URL
            
        Returns:
            Tuple[速度(MB/s), 错误信息, 响应时间]
        """
        start_time = time.time()
        
        try:
            response = self.session.get(
                url, 
                timeout=self.timeout, 
                stream=True,
                headers={'Range': f'bytes=0-{self.test_size-1}'}
            )
            response_time = time.time() - start_time
            
            if response.status_code not in [200, 206]:
                return None, f"HTTP {response.status_code}", response_time
            
            content_length = 0
            chunk_start_time = time.time()
            
            for chunk in response.iter_content(chunk_size=64*1024):  # 64KB chunks
                if not chunk:
                    break
                    
                content_length += len(chunk)
                if content_length >= self.test_size:
                    break
                    
                # 检查下载是否超时
                if time.time() - chunk_start_time > self.timeout:
                    return None, "下载超时", response_time
            
            if content_length == 0:
                return 0.0, "无数据", response_time
            
            total_time = time.time() - start_time
            speed_mbps = (content_length / total_time) / (1024 * 1024)  # MB/s
            
            return speed_mbps, None, response_time
            
        except requests.exceptions.Timeout:
            return None, "请求超时", time.time() - start_time
        except requests.exceptions.SSLError:
            return None, "SSL错误", time.time() - start_time
        except requests.exceptions.ConnectionError:
            return None, "连接失败", time.time() - start_time
        except requests.exceptions.HTTPError as e:
            return None, f"HTTP错误 {e.response.status_code}", time.time() - start_time
        except Exception as e:
            return None, f"错误: {str(e)}", time.time() - start_time

    def test_urls_concurrently(self, urls: List[str]) -> List[Tuple[str, Optional[float], Optional[str], float]]:
        """并发测试URL列表"""
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_url = {executor.submit(self.test_single_url, url): url for url in urls}
            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                speed, error, response_time = future.result()
                results.append((url, speed, error, response_time))
        return results

    def test_all_channels(self, grouped_streams: pd.DataFrame) -> Dict[str, List[Tuple[str, float]]]:
        """测试所有频道并保留最佳源"""
        keep_best = self.config.get('keep_best_sources', 5)
        min_speed = self.config.get('min_speed_mbps', 0.3)
        results = {}
        total_channels = len(grouped_streams)
        tested_channels = 0
        successful_channels = 0
        
        self.logger.info(f"开始测速 {total_channels} 个频道")
        self.logger.info(f"每个频道测试最多{self.config.get('max_sources_per_channel', 25)}个源，保留最优{keep_best}个")
        self.logger.info(f"最低速度要求: {min_speed} MB/s")
        
        for idx, (_, row) in enumerate(grouped_streams.iterrows(), 1):
            channel = row['program_name']
            urls = row['stream_url']
            
            self.logger.info(f"[{idx}/{total_channels}] 测试频道: {channel} ({len(urls)}个源)")
            
            test_results = self.test_urls_concurrently(urls)
            valid_streams = []
            
            excellent_count = 0
            good_count = 0
            slow_count = 0
            failed_count = 0
            
            for url, speed, error, response_time in test_results:
                if speed is not None:
                    if speed >= min_speed:  # 过滤低速源
                        valid_streams.append((url, speed))
                        if speed > 2.0:
                            excellent_count += 1
                        elif speed > 1.0:
                            good_count += 1
                        else:
                            slow_count += 1
                    else:
                        slow_count += 1
                else:
                    failed_count += 1
            
            # 按速度排序并保留最佳源
            valid_streams.sort(key=lambda x: x[1], reverse=True)
            best_streams = valid_streams[:keep_best]
            results[channel] = best_streams
            
            tested_channels += 1
            if best_streams:
                successful_channels += 1
                best_speed = best_streams[0][1]
                self.logger.info(f"  ✅ 成功: 最佳速度 {best_speed:.2f} MB/s")
                self.logger.info(f"     详情: 极速{excellent_count} 快速{good_count} 慢速{slow_count} 失败{failed_count}")
                self.logger.info(f"     保留: {len(best_streams)}个最优源")
            else:
                self.logger.warning(f"  ❌ 失败: 无有效源 (最低要求: {min_speed} MB/s)")
        
        self.logger.info(f"测速完成: {successful_channels}/{tested_channels} 个频道有有效源")
        return results

    # ==================== 模板匹配和结果生成 ====================
    
    def filter_by_template(self, speed_results: Dict[str, List[Tuple[str, float]]]) -> Dict[str, List[Tuple[str, float]]]:
        """根据模板频道过滤结果"""
        if not self.template_channels:
            self.logger.info("未使用模板过滤，保留所有频道")
            return speed_results
        
        filtered_results = {}
        matched_count = 0
        
        for channel in self.template_channels:
            if channel in speed_results and speed_results[channel]:
                filtered_results[channel] = speed_results[channel]
                matched_count += 1
        
        self.logger.info(f"模板匹配: {matched_count}/{len(self.template_channels)} 个频道")
        
        # 显示未匹配的模板频道
        unmatched = self.template_channels - set(speed_results.keys())
        if unmatched:
            self.logger.warning(f"未找到源的模板频道: {len(unmatched)}个")
            for channel in list(unmatched)[:10]:  # 只显示前10个
                self.logger.warning(f"  - {channel}")
            if len(unmatched) > 10:
                self.logger.warning(f"  ... 还有 {len(unmatched) - 10} 个")
        
        return filtered_results

    def generate_output_files(self, speed_results: Dict[str, List[Tuple[str, float]]]):
        """生成所有输出文件"""
        self.generate_txt_file(speed_results)
        self.generate_m3u_file(speed_results)
        self.generate_report(speed_results)

    def generate_txt_file(self, results: Dict[str, List[Tuple[str, float]]]):
        """生成TXT格式文件"""
        categories = {
            "央视频道,#genre#": ["CCTV", "央视"],
            "卫视频道,#genre#": ["卫视", "湖南", "浙江", "江苏", "东方", "北京"],
            "地方频道,#genre#": ["重庆", "广东", "深圳", "南方", "天津", "河北"],
            "港澳频道,#genre#": ["凤凰", "翡翠", "明珠", "澳亚"],
            "其他频道,#genre#": []
        }
        
        categorized = {cat: [] for cat in categories}
        
        for channel in self.get_ordered_channels(results.keys()):
            streams = results.get(channel, [])
            if not streams:
                continue
                
            matched = False
            for cat, keywords in categories.items():
                if any(keyword in channel for keyword in keywords):
                    categorized[cat].extend(
                        f"{channel},{url} # 速度: {speed:.2f}MB/s" 
                        for url, speed in streams
                    )
                    matched = True
                    break
            
            if not matched:
                categorized["其他频道,#genre#"].extend(
                    f"{channel},{url} # 速度: {speed:.2f}MB/s" 
                    for url, speed in streams
                )
        
        with open(self.output_files['txt'], 'w', encoding='utf-8') as f:
            for cat, items in categorized.items():
                if items:
                    f.write(f"\n{cat}\n")
                    f.write("\n".join(items) + "\n")
        
        self.logger.info(f"生成TXT文件: {self.output_files['txt']}")

    def generate_m3u_file(self, results: Dict[str, List[Tuple[str, float]]]):
        """生成M3U格式文件"""
        with open(self.output_files['m3u'], 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            
            for channel in self.get_ordered_channels(results.keys()):
                streams = results.get(channel, [])
                for url, speed in streams:
                    quality = self.get_speed_quality(speed)
                    f.write(f'#EXTINF:-1 tvg-name="{channel}",{channel} [速度: {speed:.2f}MB/s {quality}]\n{url}\n')
        
        self.logger.info(f"生成M3U文件: {self.output_files['m3u']}")

    def generate_report(self, results: Dict[str, List[Tuple[str, float]]]):
        """生成测速报告"""
        speed_stats = []
        valid_channels = []
        total_sources = 0
        
        for channel, streams in results.items():
            if streams:
                best_speed = streams[0][1]
                speed_stats.append(best_speed)
                valid_channels.append((channel, best_speed, len(streams)))
                total_sources += len(streams)
        
        if not speed_stats:
            self.logger.warning("⚠️ 无有效测速结果")
            return
        
        # 按速度排序频道
        valid_channels.sort(key=lambda x: x[1], reverse=True)
        
        print("\n" + "="*60)
        print("IPTV直播源测速报告")
        print("="*60)
        print(f"有效频道数: {len(valid_channels)}")
        print(f"总源数量: {total_sources}")
        print(f"平均速度: {sum(speed_stats)/len(speed_stats):.2f} MB/s")
        print(f"最快速度: {max(speed_stats):.2f} MB/s")
        print(f"最慢速度: {min(speed_stats):.2f} MB/s")
        print(f"速度要求: ≥{self.min_speed_mbps} MB/s")
        
        # 速度分布统计
        excellent = len([s for s in speed_stats if s > 2.0])
        good = len([s for s in speed_stats if 1.0 < s <= 2.0])
        normal = len([s for s in speed_stats if 0.5 < s <= 1.0])
        slow = len([s for s in speed_stats if s <= 0.5])
        
        print(f"\n速度分布:")
        print(f"  极速(>2.0MB/s): {excellent}个频道")
        print(f"  快速(1.0-2.0MB/s): {good}个频道")
        print(f"  中速(0.5-1.0MB/s): {normal}个频道")
        print(f"  慢速(≤0.5MB/s): {slow}个频道")
        
        print("\n频道速度排名 TOP 20:")
        for i, (channel, speed, count) in enumerate(valid_channels[:20], 1):
            quality = self.get_speed_quality(speed)
            print(f"{i:2d}. {channel:<15} {speed:>5.2f} MB/s ({quality}) [{count}个源]")

    # ==================== 辅助方法 ====================
    
    def get_ordered_channels(self, channels: List[str]) -> List[str]:
        """按照模板顺序排序频道列表"""
        if not self.template_channels:
            return sorted(channels)
        
        ordered = []
        # 首先按模板顺序
        with open(self.template_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if match := self.channel_pattern.match(line):
                        channel = self.normalize_channel_name(match.group(1).strip())
                        if channel in channels and channel not in ordered:
                            ordered.append(channel)
        
        # 添加未在模板中的频道（理论上不应该有，因为已经过滤了）
        for channel in channels:
            if channel not in ordered:
                ordered.append(channel)
                
        return ordered

    def _extract_domain(self, url: str) -> str:
        """从URL提取域名"""
        try:
            netloc = urlparse(url).netloc
            return netloc.split(':')[0]
        except:
            return url[:30] + "..." if len(url) > 30 else url

    def get_speed_quality(self, speed: float) -> str:
        """获取速度质量评级"""
        if speed > 2.0: return "极佳"
        if speed > 1.0: return "优秀" 
        if speed > 0.5: return "良好"
        if speed > 0.3: return "一般"
        return "较差"

    # ==================== 主流程 ====================
    
    def run(self):
        """运行主流程"""
        print("="*60)
        print("IPTV直播源处理工具")
        print("="*60)
        print(f"配置: 超时{self.timeout}s 线程{self.max_workers} 测速{self.test_size//1024}KB")
        print(f"要求: 最低速度{self.min_speed_mbps}MB/s")
        
        start_time = time.time()
        
        try:
            # 第一步：抓取所有直播源
            self.logger.info("第一步：抓取直播源...")
            content = self.fetch_streams()
            if not content:
                self.logger.error("❌ 未能获取有效数据")
                return
            
            # 第二步：解析和整理数据
            self.logger.info("第二步：解析直播源数据...")
            df = self.parse_content(content)
            if df.empty:
                self.logger.error("❌ 未解析到有效直播源")
                return
            
            # 第三步：整理数据，每个频道最多指定数量的源
            grouped = self.organize_streams(df)
            
            # 第四步：对所有频道进行测速
            self.logger.info("第三步：测速优化...")
            speed_results = self.test_all_channels(grouped)
            
            # 第五步：根据模板频道过滤结果
            self.logger.info("第四步：模板匹配...")
            filtered_results = self.filter_by_template(speed_results)
            
            if not filtered_results:
                self.logger.error("❌ 无匹配的频道结果")
                return
            
            # 第六步：生成输出文件
            self.logger.info("第五步：生成输出文件...")
            self.generate_output_files(filtered_results)
            
            # 完成统计
            total_time = time.time() - start_time
            self.logger.info(f"🎉 处理完成! 总耗时: {total_time:.1f}秒")
            
        except KeyboardInterrupt:
            self.logger.info("用户中断程序")
        except Exception as e:
            self.logger.error(f"❌ 处理过程中发生错误: {str(e)}")
            import traceback
            traceback.print_exc()


def main():
    """主程序入口"""
    parser = argparse.ArgumentParser(description='IPTV直播源处理工具')
    parser.add_argument('--config', '-c', default='config.json', help='配置文件路径')
    parser.add_argument('--timeout', '-t', type=int, help='超时时间(秒)')
    parser.add_argument('--workers', '-w', type=int, help='并发线程数')
    parser.add_argument('--test-size', '-s', type=int, help='测速数据大小(KB)')
    parser.add_argument('--min-speed', type=float, help='最低速度要求(MB/s)')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细日志输出')
    
    args = parser.parse_args()
    
    # 设置日志级别
    log_level = logging.DEBUG if args.verbose else logging.INFO
    
    try:
        # 创建IPTV实例
        tool = IPTV(args.config)
        
        # 覆盖命令行参数
        if args.timeout:
            tool.timeout = args.timeout
        if args.workers:
            tool.max_workers = args.workers
        if args.test_size:
            tool.test_size = args.test_size * 1024
        if args.min_speed:
            tool.min_speed_mbps = args.min_speed
        
        # 运行主流程
        tool.run()
        
    except KeyboardInterrupt:
        print("\n用户中断程序")
    except Exception as e:
        print(f"程序执行错误: {e}")
        logging.exception("程序异常")


if __name__ == "__main__":
    main()
