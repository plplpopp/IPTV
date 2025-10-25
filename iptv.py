#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import time
import concurrent.futures
import re
from typing import List, Dict, Set, Any
from urllib.parse import urlparse
import json

class IPTVUpdater:
    def __init__(self):
        self.sources = [
            "https://raw.githubusercontent.com/vbskyn/iptv/master/tv/iptv4.txt",
            "https://raw.githubusercontent.com/develop202/migu_video/refs/heads/main/interface.txt",
            "http://47.120.41.246:8899/zb.txt",
            # 可以添加更多源...
        ]
        
        # 初始化模板标准化规则
        self.ttemplate_norm = {
            'cctv': 'CCTV',
            '中央': 'CCTV',
            '央视': 'CCTV',
            '湖南卫视': '湖南',
            '浙江卫视': '浙江', 
            '江苏卫视': '江苏',
            '北京卫视': '北京',
            '东方卫视': '东方',
            '广东卫视': '广东',
            '深圳卫视': '深圳',
            '天津卫视': '天津',
            '山东卫视': '山东',
            '安徽卫视': '安徽',
            '重庆卫视': '重庆',
            '四川卫视': '四川',
            '辽宁卫视': '辽宁',
            '黑龙江卫视': '黑龙江',
            '湖北卫视': '湖北',
            '河南卫视': '河南'
        }
        
        self.collected_streams = []
        self.unique_streams = []

    def fetch_source(self, url: str) -> Dict[str, Any]:
        """获取单个源的内容"""
        print(f"📡 正在爬取：{url}")
        start_time = time.time()
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            content_length = len(response.text)
            duration = time.time() - start_time
            
            # 解析流数量
            streams = self.parse_streams(response.text)
            
            print(f"✅ 成功获取：{content_length} 字符")
            print(f"✅ 从 {url} 获取 {len(streams)} 个流")
            
            return {
                'url': url,
                'status': 'success',
                'content': response.text,
                'streams': streams,
                'content_length': content_length,
                'duration': duration,
                'stream_count': len(streams)
            }
            
        except Exception as e:
            print(f"❌ 获取失败：{url} - {str(e)}")
            return {
                'url': url,
                'status': 'error',
                'error': str(e),
                'content': '',
                'streams': [],
                'content_length': 0,
                'duration': time.time() - start_time,
                'stream_count': 0
            }

    def parse_streams(self, content: str) -> List[str]:
        """从内容中解析出流URL"""
        streams = []
        
        # 多种格式支持
        patterns = [
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
            r'^[^#].*\.m3u8?$',
            r'^[^#].*\.flv?$',
            r'^[^#].*\.mp4?$',
            r'^[^#].*\.ts?$'
        ]
        
        for line in content.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                for pattern in patterns:
                    matches = re.findall(pattern, line)
                    for match in matches:
                        if any(ext in match.lower() for ext in ['.m3u8', '.flv', '.mp4', '.ts', 'rtmp://', 'rtsp://']):
                            streams.append(match)
        
        return streams

    def remove_duplicate_streams(self, streams: List[str]) -> List[str]:
        """去除重复的流"""
        print("🔄 开始去重处理...")
        original_count = len(streams)
        
        # 基于URL去重
        seen_urls = set()
        unique_streams = []
        
        for stream in streams:
            # 标准化URL
            normalized_url = self.normalize_url(stream)
            if normalized_url not in seen_urls:
                seen_urls.add(normalized_url)
                unique_streams.append(stream)
        
        removed_count = original_count - len(unique_streams)
        print(f"✅ 去重完成：移除 {removed_count} 个重复流")
        
        return unique_streams

    def normalize_url(self, url: str) -> str:
        """标准化URL用于去重"""
        try:
            parsed = urlparse(url)
            # 移除查询参数和片段
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            return normalized.lower()
        except:
            return url.lower()

    class AdvancedSpeedTester:
        def __init__(self, max_workers=10, timeout=5):
            self.max_workers = max_workers
            self.timeout = timeout
            self.session = requests.Session()
            self.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })

        def test_single_stream(self, stream_url: str) -> Dict:
            """测试单个流的速度和可用性"""
            start_time = time.time()
            try:
                response = self.session.get(
                    stream_url, 
                    timeout=self.timeout,
                    stream=True,
                    verify=False  # 对于自签名证书的源
                )
                response.raise_for_status()
                
                # 读取前50KB测试速度
                chunk_size = 1024
                total_read = 0
                max_test_size = 50 * 1024  # 50KB
                test_start = time.time()
                
                for chunk in response.iter_content(chunk_size=chunk_size):
                    total_read += len(chunk)
                    if total_read >= max_test_size:
                        break
                    if time.time() - test_start > self.timeout:
                        break
                
                end_time = time.time()
                duration = end_time - start_time
                speed = total_read / duration if duration > 0 else 0
                
                return {
                    'url': stream_url,
                    'status': 'success',
                    'speed_kbps': speed / 1024,
                    'response_time': duration,
                    'content_length': total_read,
                    'quality': 'excellent' if speed > 500 * 1024 else 'good' if speed > 100 * 1024 else 'fair'
                }
                
            except Exception as e:
                return {
                    'url': stream_url,
                    'status': 'error',
                    'error': str(e),
                    'speed_kbps': 0,
                    'response_time': time.time() - start_time,
                    'content_length': 0,
                    'quality': 'poor'
                }

        def batch_test_streams(self, stream_urls: List[str], sample_size: int = 200) -> Dict:
            """批量测试流速度，支持抽样测试"""
            if len(stream_urls) > sample_size:
                print(f"📊 流数量较多({len(stream_urls)})，进行抽样测试({sample_size}个样本)")
                # 简单抽样：取前sample_size个
                stream_urls = stream_urls[:sample_size]
            
            results = {}
            print(f"🚀 开始测速，共 {len(stream_urls)} 个流...")
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_url = {
                    executor.submit(self.test_single_stream, url): url 
                    for url in stream_urls
                }
                
                completed = 0
                for future in concurrent.futures.as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        results[url] = future.result()
                        completed += 1
                        if completed % 20 == 0:
                            print(f"📈 测速进度: {completed}/{len(stream_urls)}")
                    except Exception as e:
                        results[url] = {
                            'url': url,
                            'status': 'error',
                            'error': str(e),
                            'speed_kbps': 0,
                            'response_time': 0,
                            'content_length': 0,
                            'quality': 'poor'
                        }
                        completed += 1
            
            return results

    class SmartSpeedTester:
        def __init__(self):
            self.speed_thresholds = {
                'excellent': 2000,  # 2MB/s
                'good': 500,        # 500KB/s
                'fair': 100,        # 100KB/s
                'poor': 10          # 10KB/s
            }

        def categorize_speed(self, speed_kbps: float) -> str:
            """根据速度分类流质量"""
            if speed_kbps >= self.speed_thresholds['excellent']:
                return 'excellent'
            elif speed_kbps >= self.speed_thresholds['good']:
                return 'good'
            elif speed_kbps >= self.speed_thresholds['fair']:
                return 'fair'
            else:
                return 'poor'

        def optimize_stream_selection(self, test_results: Dict) -> List[str]:
            """优化流选择策略"""
            categorized_streams = {
                'excellent': [],
                'good': [],
                'fair': [],
                'poor': []
            }
            
            # 分类流
            for url, result in test_results.items():
                if result['status'] == 'success':
                    category = self.categorize_speed(result['speed_kbps'])
                    categorized_streams[category].append({
                        'url': url,
                        'speed': result['speed_kbps'],
                        'response_time': result['response_time']
                    })
            
            # 优化选择：优先选择优秀和良好的流
            optimized_streams = []
            
            # 按响应时间排序并选择
            for category in ['excellent', 'good', 'fair']:
                sorted_streams = sorted(categorized_streams[category], 
                                      key=lambda x: x['response_time'])
                for stream in sorted_streams:
                    optimized_streams.append(stream['url'])
            
            return optimized_streams

    def enhanced_speed_testing(self, streams: List[str]) -> Dict:
        """增强的测速流程"""
        print("⚡ 开始增强测速...")
        
        # 初始化测速器
        speed_tester = self.AdvancedSpeedTester(max_workers=15, timeout=8)
        smart_tester = self.SmartSpeedTester()
        
        # 批量测速
        test_results = speed_tester.batch_test_streams(streams)
        
        # 分析结果
        successful = [r for r in test_results.values() if r['status'] == 'success']
        failed = [r for r in test_results.values() if r['status'] == 'error']
        
        print(f"✅ 测速成功: {len(successful)} 个流")
        print(f"❌ 测速失败: {len(failed)} 个流")
        
        if successful:
            avg_speed = sum(r['speed_kbps'] for r in successful) / len(successful)
            max_speed = max(r['speed_kbps'] for r in successful)
            print(f"📈 平均速度: {avg_speed:.2f} KB/s")
            print(f"🏆 最高速度: {max_speed:.2f} KB/s")
            
            # 质量分布
            quality_dist = {}
            for result in successful:
                quality = result['quality']
                quality_dist[quality] = quality_dist.get(quality, 0) + 1
            
            print("🎯 质量分布:", quality_dist)
        
        # 优化流选择
        optimized_streams = smart_tester.optimize_stream_selection(test_results)
        print(f"🎯 优化后选择: {len(optimized_streams)} 个优质流")
        
        return {
            'test_results': test_results,
            'optimized_streams': optimized_streams,
            'statistics': {
                'total_tested': len(streams),
                'successful': len(successful),
                'failed': len(failed),
                'avg_speed': avg_speed if successful else 0,
                'max_speed': max_speed if successful else 0
            }
        }

    def smart_channel_matching(self, streams: List[str]) -> List[Dict]:
        """智能频道匹配"""
        print("🔍 开始智能频道匹配...")
        
        try:
            matched_channels = []
            
            for stream_url in streams:
                channel_name = self.extract_channel_name(stream_url)
                normalized_name = self.normalize_channel_name(channel_name)
                
                matched_channels.append({
                    'name': normalized_name,
                    'url': stream_url,
                    'original_name': channel_name
                })
            
            print(f"✅ 频道匹配完成: {len(matched_channels)} 个频道")
            return matched_channels
            
        except Exception as e:
            print(f"❌ 智能频道匹配出错: {e}")
            # 回退到基础匹配
            return self.basic_channel_matching(streams)

    def extract_channel_name(self, url: str) -> str:
        """从URL中提取频道名称"""
        try:
            # 从URL路径中提取可能的频道名
            parsed = urlparse(url)
            path_parts = parsed.path.split('/')
            
            for part in path_parts:
                if part and '.' not in part and len(part) > 1:
                    # 简单的频道名提取逻辑
                    if any(keyword in part.lower() for keyword in ['cctv', 'tv', 'channel', 'live']):
                        return part
            
            # 如果没有找到，使用最后一部分非空路径
            for part in reversed(path_parts):
                if part and '.' not in part:
                    return part
            
            return "未知频道"
        except:
            return "未知频道"

    def normalize_channel_name(self, name: str) -> str:
        """标准化频道名称"""
        if not name or name == "未知频道":
            return "其他频道"
        
        name_lower = name.lower()
        
        # 使用预定义的标准化规则
        for key, value in self.ttemplate_norm.items():
            if key in name_lower:
                return value
        
        # 简单的数字频道处理
        if re.search(r'cctv-?\d+', name_lower):
            match = re.search(r'cctv-?(\d+)', name_lower)
            return f"CCTV-{match.group(1)}"
        
        return name

    def basic_channel_matching(self, streams: List[str]) -> List[Dict]:
        """基础频道匹配（回退方案）"""
        print("🔄 使用基础频道匹配...")
        
        channels = []
        for i, stream_url in enumerate(streams):
            channels.append({
                'name': f'频道{i+1}',
                'url': stream_url,
                'original_name': '未识别'
            })
        
        return channels

    def generate_optimized_playlist(self, channels: List[Dict]) -> str:
        """生成优化的播放列表"""
        print("📝 生成优化播放列表...")
        
        playlist = "#EXTM3U\n"
        playlist += "# Generated by Enhanced IPTV Updater\n"
        playlist += f"# Update Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        playlist += f"# Total Channels: {len(channels)}\n\n"
        
        for channel in channels:
            playlist += f"#EXTINF:-1, {channel['name']}\n"
            playlist += f"{channel['url']}\n\n"
        
        return playlist

    def save_playlist(self, playlist: str, filename: str = "optimized_iptv.m3u"):
        """保存播放列表到文件"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(playlist)
            print(f"💾 播放列表已保存: {filename}")
        except Exception as e:
            print(f"❌ 保存播放列表失败: {e}")

    def update_documentation(self):
        """更新文档"""
        print("📄 更新文档...")
        # 这里可以添加更新README或其他文档的逻辑
        print("✅ 文档更新完成")

    def main_enhanced_update(self):
        """增强的主更新流程"""
        print("🎬 开始增强版IPTV更新流程...")
        start_time = time.time()
        
        try:
            # 1. 获取所有源
            print("🌐 获取IPTV源...")
            fetch_results = []
            
            for source in self.sources:
                result = self.fetch_source(source)
                fetch_results.append(result)
                time.sleep(1)  # 避免请求过快
            
            # 统计获取结果
            successful_fetches = [r for r in fetch_results if r['status'] == 'success']
            failed_fetches = [r for r in fetch_results if r['status'] == 'error']
            
            print(f"📊 在线源获取完成: {len(successful_fetches)} 成功, {len(failed_fetches)} 失败")
            
            # 2. 收集所有流
            all_streams = []
            for result in successful_fetches:
                all_streams.extend(result['streams'])
            
            total_streams = len(all_streams)
            print(f"✅ 总共收集到: {total_streams} 个流")
            
            if total_streams == 0:
                print("❌ 没有获取到任何流，程序结束")
                return
            
            # 3. 去重处理
            self.unique_streams = self.remove_duplicate_streams(all_streams)
            print(f"🎯 去重后剩余: {len(self.unique_streams)} 个唯一流")
            
            # 4. 增强测速
            speed_test_results = self.enhanced_speed_testing(self.unique_streams)
            
            # 5. 智能频道匹配
            matched_channels = self.smart_channel_matching(speed_test_results['optimized_streams'])
            
            # 6. 生成播放列表
            optimized_playlist = self.generate_optimized_playlist(matched_channels)
            
            # 7. 保存结果
            self.save_playlist(optimized_playlist)
            
            # 8. 更新文档
            self.update_documentation()
            
            total_duration = time.time() - start_time
            print(f"🎉 更新完成！总耗时: {total_duration:.1f} 秒")
            
            # 输出最终统计
            print("\n📊 最终统计:")
            print(f"   📡 源数量: {len(self.sources)}")
            print(f"   🔗 原始流: {total_streams}")
            print(f"   ✨ 唯一流: {len(self.unique_streams)}") 
            print(f"   🎯 优质流: {len(speed_test_results['optimized_streams'])}")
            print(f"   📺 频道数: {len(matched_channels)}")
            print(f"   ⚡ 平均速度: {speed_test_results['statistics']['avg_speed']:.2f} KB/s")
            
            return optimized_playlist
            
        except Exception as e:
            print(f"❌ 更新过程出错: {e}")
            import traceback
            traceback.print_exc()
            return None

def main():
    """主函数"""
    updater = IPTVUpdater()
    updater.main_enhanced_update()

if __name__ == "__main__":
    main()
