"""
Benchmarking Script for Kafka ML Inference Pipeline

Measures:
1. Inference throughput (images/second)
2. Classification accuracy (predicted vs ground truth)
3. Multi-process vs single-threaded comparison
4. Latency statistics (min, max, avg, p95, p99)

Usage:
    python benchmark.py --mode multi      # Benchmark multi-process (default)
    python benchmark.py --mode single     # Benchmark single-threaded
    python benchmark.py --mode compare    # Run both and compare
    python benchmark.py --duration 120    # Run for 120 seconds (default: 60)
"""

import json
import time
import queue
import logging
import os
import argparse
import cv2
import torch
import torch.multiprocessing as mp
import numpy as np
from torchvision import models, transforms
from confluent_kafka import Consumer
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import List
import statistics

load_dotenv()

# Config
TOPIC = os.getenv('KAFKA_TOPIC', 'image_data')
BATCH_SIZE = int(os.getenv('BATCH_SIZE', 8))
QUEUE_SIZE = int(os.getenv('QUEUE_SIZE', 200))
KAFKA_BROKER = os.getenv('KAFKA_BOOTSTRAP_SERVER', 'localhost:9092')
KAFKA_CONSUMER_GROUP = 'benchmark_group'  # Separate from main consumer to avoid message competition
MODEL_PATH = os.getenv('MODEL_PATH', 'model.pth')
CLASSES_PATH = os.getenv('CLASSES_PATH', 'classes.json')

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)


@dataclass
class BenchmarkMetrics:
    """Container for benchmark results."""
    mode: str
    duration: float = 0.0
    images_processed: int = 0
    correct_predictions: int = 0
    latencies: List[float] = field(default_factory=list)
    inference_times: List[float] = field(default_factory=list)
    confidences: List[float] = field(default_factory=list)
    # Pre-computed values (for multi-process mode)
    _latency_p95: float = 0.0
    _latency_p99: float = 0.0
    _confidence_min: float = 0.0
    
    @property
    def throughput(self) -> float:
        if self.duration == 0:
            return 0.0
        return self.images_processed / self.duration
    
    @property
    def accuracy(self) -> float:
        if self.images_processed == 0:
            return 0.0
        return (self.correct_predictions / self.images_processed) * 100
    
    @property
    def avg_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        return statistics.mean(self.latencies) * 1000
    
    @property
    def p95_latency_ms(self) -> float:
        if self._latency_p95 > 0:
            return self._latency_p95 * 1000
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[idx] * 1000
    
    @property
    def p99_latency_ms(self) -> float:
        if self._latency_p99 > 0:
            return self._latency_p99 * 1000
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[idx] * 1000
    
    @property
    def avg_confidence(self) -> float:
        if not self.confidences:
            return 0.0
        return statistics.mean(self.confidences) * 100
    
    @property
    def min_confidence(self) -> float:
        if self._confidence_min > 0:
            return self._confidence_min * 100
        if not self.confidences:
            return 0.0
        return min(self.confidences) * 100
    
    @property
    def avg_inference_time_ms(self) -> float:
        if not self.inference_times:
            return 0.0
        return statistics.mean(self.inference_times) * 1000
    
    def print_report(self):
        print("\n" + "=" * 60)
        print(f"BENCHMARK RESULTS: {self.mode.upper()} MODE")
        print("=" * 60)
        print(f"Duration:            {self.duration:.2f} seconds")
        print(f"Images Processed:    {self.images_processed}")
        print(f"Correct Predictions: {self.correct_predictions}")
        print("-" * 60)
        print(f"THROUGHPUT:          {self.throughput:.2f} images/sec")
        print(f"ACCURACY:            {self.accuracy:.2f}%")
        print("-" * 60)
        print(f"Avg Latency:         {self.avg_latency_ms:.2f} ms")
        print(f"P95 Latency:         {self.p95_latency_ms:.2f} ms")
        print(f"P99 Latency:         {self.p99_latency_ms:.2f} ms")
        print(f"Avg Inference Time:  {self.avg_inference_time_ms:.2f} ms")
        print("-" * 60)
        print(f"Avg Confidence:      {self.avg_confidence:.2f}%")
        print(f"Min Confidence:      {self.min_confidence:.2f}%")
        print("=" * 60 + "\n")


def load_model():
    """Load the trained model and class labels."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logging.info(f"Using device: {device}")
    
    if not os.path.exists(CLASSES_PATH) or not os.path.exists(MODEL_PATH):
        logging.error("Model or classes file not found. Run train.py first.")
        return None, None, None
    
    with open(CLASSES_PATH, 'r') as f:
        idx_to_label = json.load(f)
        idx_to_label = {int(k): v for k, v in idx_to_label.items()}
    
    model = models.mobilenet_v2(weights=None)
    model.classifier[1] = torch.nn.Linear(model.last_channel, len(idx_to_label))
    model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
    model.to(device)
    model.eval()
    
    preprocess = transforms.Compose([
        transforms.ToPILImage(),
        transforms.Resize(224),
        transforms.ToTensor(),
    ])
    
    return model, idx_to_label, preprocess


def decode_message(raw_bytes):
    """Decode Kafka message into image and metadata."""
    header_len = int.from_bytes(raw_bytes[:4], byteorder='big')
    meta_json = raw_bytes[4:4 + header_len]
    metadata = json.loads(meta_json)
    
    img_bytes = raw_bytes[4 + header_len:]
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    return img, metadata


# =============================================================================
# SINGLE-THREADED BENCHMARK
# =============================================================================

def benchmark_single_threaded(duration_seconds: int) -> BenchmarkMetrics:
    """Run single-threaded benchmark (fetch + inference in same thread)."""
    logging.info("Starting SINGLE-THREADED benchmark...")
    
    metrics = BenchmarkMetrics(mode="single-threaded")
    
    model, idx_to_label, preprocess = load_model()
    if model is None:
        return metrics
    
    device = next(model.parameters()).device
    
    consumer = Consumer({
        'bootstrap.servers': KAFKA_BROKER,
        'group.id': f'{KAFKA_CONSUMER_GROUP}_single_{int(time.time())}',
        'auto.offset.reset': 'latest'
    })
    consumer.subscribe([TOPIC])
    
    # Warm-up: wait for first message
    logging.info("Waiting for messages (ensure producer is running)...")
    while True:
        msg = consumer.poll(1.0)
        if msg and not msg.error():
            break
    
    logging.info(f"Running benchmark for {duration_seconds} seconds...")
    
    batch_imgs = []
    batch_metas = []
    start_time = time.time()
    
    while (time.time() - start_time) < duration_seconds:
        msg = consumer.poll(0.1)
        
        if msg is None or msg.error():
            continue
        
        try:
            img, metadata = decode_message(msg.value())
            batch_imgs.append(img)
            batch_metas.append(metadata)
            
            if len(batch_imgs) >= BATCH_SIZE:
                batch_start = time.time()
                
                # Preprocess
                tensors = []
                for b_img in batch_imgs:
                    rgb_img = cv2.cvtColor(b_img, cv2.COLOR_BGR2RGB)
                    tensors.append(preprocess(rgb_img))
                
                batch_t = torch.stack(tensors).to(device)
                
                # Inference
                with torch.no_grad():
                    outputs = model(batch_t)
                    probs = torch.nn.functional.softmax(outputs, dim=1)
                    top_conf, top_class_idx = torch.max(probs, dim=1)
                
                conf_np = top_conf.cpu().numpy()
                idx_np = top_class_idx.cpu().numpy()
                
                batch_latency = time.time() - batch_start
                
                # Calculate metrics
                for i in range(len(batch_imgs)):
                    predicted = idx_to_label[idx_np[i]].strip()
                    ground_truth = f"{batch_metas[i]['color_label']}_{batch_metas[i]['shape_label']}"
                    
                    metrics.images_processed += 1
                    metrics.latencies.append(batch_latency / len(batch_imgs))
                    metrics.inference_times.append(batch_latency / len(batch_imgs))
                    metrics.confidences.append(conf_np[i])
                    
                    if predicted == ground_truth:
                        metrics.correct_predictions += 1
                
                # Progress update
                if metrics.images_processed % 100 == 0:
                    elapsed = time.time() - start_time
                    current_throughput = metrics.images_processed / elapsed
                    logging.info(f"Processed: {metrics.images_processed} | "
                               f"Throughput: {current_throughput:.2f} img/s | "
                               f"Accuracy: {metrics.accuracy:.2f}%")
                
                batch_imgs = []
                batch_metas = []
                
        except Exception as e:
            logging.error(f"Error: {e}")
            batch_imgs = []
            batch_metas = []
    
    metrics.duration = time.time() - start_time
    consumer.close()
    
    return metrics


# =============================================================================
# MULTI-PROCESS BENCHMARK
# =============================================================================

def fetch_process(data_queue: mp.Queue, running_event: mp.Event, stats_queue: mp.Queue):
    """Network fetcher process."""
    consumer = Consumer({
        'bootstrap.servers': KAFKA_BROKER,
        'group.id': f'{KAFKA_CONSUMER_GROUP}_multi_{int(time.time())}',
        'auto.offset.reset': 'latest'
    })
    consumer.subscribe([TOPIC])
    
    messages_fetched = 0
    
    try:
        while running_event.is_set():
            msg = consumer.poll(0.1)
            
            if msg is None or msg.error():
                continue
            
            try:
                img, metadata = decode_message(msg.value())
                metadata['fetch_time'] = time.time()
                
                # Non-blocking put with timeout, skip if queue is full
                try:
                    data_queue.put((img, metadata), timeout=0.1)
                    messages_fetched += 1
                except:
                    pass  # Queue full, skip this message
                    
            except Exception:
                pass
    finally:
        try:
            stats_queue.put({'fetched': messages_fetched}, timeout=1.0)
        except:
            pass
        consumer.close()


def inference_process(data_queue: mp.Queue, running_event: mp.Event, 
                      stats_queue: mp.Queue, duration_seconds: int):
    """GPU inference process."""
    model, idx_to_label, preprocess = load_model()
    if model is None:
        stats_queue.put({'error': 'Model not found'})
        return
    
    device = next(model.parameters()).device
    
    images_processed = 0
    correct_predictions = 0
    
    # Use running stats instead of storing all values
    latency_sum = 0.0
    latency_max = 0.0
    inference_time_sum = 0.0
    confidence_sum = 0.0
    confidence_min = 1.0
    all_latencies = []  # Keep for percentile calculation, but limit size
    
    batch_imgs = []
    batch_metas = []
    
    # Wait for first message with timeout
    logging.info("Waiting for messages...")
    wait_start = time.time()
    while running_event.is_set() and (time.time() - wait_start) < 30:  # 30 sec timeout
        try:
            img, meta = data_queue.get(timeout=1.0)
            batch_imgs.append(img)
            batch_metas.append(meta)
            break
        except queue.Empty:
            continue
    
    if not batch_imgs:
        logging.error("No messages received within timeout")
        stats_queue.put({
            'images_processed': 0,
            'correct_predictions': 0,
            'latency_avg': 0,
            'latency_p95': 0,
            'latency_p99': 0,
            'inference_time_avg': 0,
            'confidence_avg': 0,
            'confidence_min': 0,
            'duration': 0
        })
        return
    
    logging.info(f"Running benchmark for {duration_seconds} seconds...")
    start_time = time.time()
    
    try:
        while (time.time() - start_time) < duration_seconds:
            try:
                img, meta = data_queue.get(timeout=0.5)
                batch_imgs.append(img)
                batch_metas.append(meta)
                
                if len(batch_imgs) >= BATCH_SIZE:
                    batch_start = time.time()
                    
                    # Preprocess
                    tensors = []
                    for b_img in batch_imgs:
                        rgb_img = cv2.cvtColor(b_img, cv2.COLOR_BGR2RGB)
                        tensors.append(preprocess(rgb_img))
                    
                    batch_t = torch.stack(tensors).to(device)
                    
                    # Inference
                    with torch.no_grad():
                        outputs = model(batch_t)
                        probs = torch.nn.functional.softmax(outputs, dim=1)
                        top_conf, top_class_idx = torch.max(probs, dim=1)
                    
                    conf_np = top_conf.cpu().numpy()
                    idx_np = top_class_idx.cpu().numpy()
                    
                    inference_time = time.time() - batch_start
                    
                    # Calculate metrics
                    for i in range(len(batch_imgs)):
                        predicted = idx_to_label[idx_np[i]].strip()
                        ground_truth = f"{batch_metas[i]['color_label']}_{batch_metas[i]['shape_label']}"
                        
                        # End-to-end latency (from fetch to inference complete)
                        e2e_latency = time.time() - batch_metas[i]['fetch_time']
                        
                        # Running stats
                        latency_sum += e2e_latency
                        latency_max = max(latency_max, e2e_latency)
                        inference_time_sum += inference_time / len(batch_imgs)
                        confidence_sum += conf_np[i]
                        confidence_min = min(confidence_min, conf_np[i])
                        
                        # Sample latencies for percentile (keep max 1000 samples)
                        if len(all_latencies) < 1000 or images_processed % 10 == 0:
                            if len(all_latencies) >= 1000:
                                all_latencies.pop(0)
                            all_latencies.append(e2e_latency)
                        
                        images_processed += 1
                        
                        if predicted == ground_truth:
                            correct_predictions += 1
                    
                    # Progress update
                    if images_processed % 100 == 0:
                        elapsed = time.time() - start_time
                        current_throughput = images_processed / elapsed
                        current_accuracy = (correct_predictions / images_processed) * 100
                        logging.info(f"Processed: {images_processed} | "
                                   f"Throughput: {current_throughput:.2f} img/s | "
                                   f"Accuracy: {current_accuracy:.2f}%")
                    
                    batch_imgs = []
                    batch_metas = []
                    
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Inference error: {e}")
                batch_imgs = []
                batch_metas = []
    finally:
        running_event.clear()
        
        # Calculate final stats
        if images_processed > 0:
            sorted_latencies = sorted(all_latencies)
            p95_idx = int(len(sorted_latencies) * 0.95)
            p99_idx = int(len(sorted_latencies) * 0.99)
            
            stats_queue.put({
                'images_processed': images_processed,
                'correct_predictions': correct_predictions,
                'latency_avg': latency_sum / images_processed,
                'latency_p95': sorted_latencies[p95_idx] if sorted_latencies else 0,
                'latency_p99': sorted_latencies[p99_idx] if sorted_latencies else 0,
                'inference_time_avg': inference_time_sum / images_processed,
                'confidence_avg': confidence_sum / images_processed,
                'confidence_min': confidence_min,
                'duration': time.time() - start_time
            })
        else:
            stats_queue.put({
                'images_processed': 0,
                'correct_predictions': 0,
                'latency_avg': 0,
                'latency_p95': 0,
                'latency_p99': 0,
                'inference_time_avg': 0,
                'confidence_avg': 0,
                'confidence_min': 0,
                'duration': 0
            })


def benchmark_multi_process(duration_seconds: int) -> BenchmarkMetrics:
    """Run multi-process benchmark (separate fetch and inference processes)."""
    logging.info("Starting MULTI-PROCESS benchmark...")
    
    metrics = BenchmarkMetrics(mode="multi-process")
    
    mp.set_start_method('spawn', force=True)
    data_queue = mp.Queue(maxsize=QUEUE_SIZE)
    running_event = mp.Event()
    stats_queue = mp.Queue()
    running_event.set()
    
    fetcher = mp.Process(target=fetch_process, args=(data_queue, running_event, stats_queue))
    inference = mp.Process(target=inference_process, 
                          args=(data_queue, running_event, stats_queue, duration_seconds))
    
    fetcher.start()
    inference.start()
    
    # Wait for inference to complete with timeout
    inference.join(timeout=duration_seconds + 60)
    
    # Signal fetcher to stop
    running_event.clear()
    
    # Give fetcher time to finish gracefully
    fetcher.join(timeout=5)
    
    # Force terminate if still alive
    if fetcher.is_alive():
        fetcher.terminate()
        fetcher.join(timeout=2)
    
    if inference.is_alive():
        inference.terminate()
        inference.join(timeout=2)
    
    # Drain the data queue to prevent blocking
    try:
        while not data_queue.empty():
            data_queue.get_nowait()
    except:
        pass
    
    # Collect stats with timeout
    try:
        stats = stats_queue.get(timeout=5.0)
        if 'images_processed' in stats:
            metrics.images_processed = stats['images_processed']
            metrics.correct_predictions = stats['correct_predictions']
            metrics.duration = stats['duration']
            # Store pre-computed stats as single-element lists for property compatibility
            if stats['latency_avg'] > 0:
                metrics.latencies = [stats['latency_avg']]
                metrics.inference_times = [stats['inference_time_avg']]
                metrics.confidences = [stats['confidence_avg']]
                # Override properties with actual values using private attributes
                metrics._latency_p95 = stats['latency_p95']
                metrics._latency_p99 = stats['latency_p99']
                metrics._confidence_min = stats['confidence_min']
    except:
        logging.warning("Could not retrieve stats from inference process")
    
    # Close queues
    data_queue.close()
    stats_queue.close()
    
    return metrics


# =============================================================================
# COMPARISON
# =============================================================================

def print_comparison(single: BenchmarkMetrics, multi: BenchmarkMetrics):
    """Print side-by-side comparison of benchmarks."""
    speedup = multi.throughput / single.throughput if single.throughput > 0 else 0
    
    print("\n" + "=" * 70)
    print("BENCHMARK COMPARISON: SINGLE-THREADED vs MULTI-PROCESS")
    print("=" * 70)
    print(f"{'Metric':<25} {'Single-Threaded':>20} {'Multi-Process':>20}")
    print("-" * 70)
    print(f"{'Duration (s)':<25} {single.duration:>20.2f} {multi.duration:>20.2f}")
    print(f"{'Images Processed':<25} {single.images_processed:>20} {multi.images_processed:>20}")
    print(f"{'Throughput (img/s)':<25} {single.throughput:>20.2f} {multi.throughput:>20.2f}")
    print(f"{'Accuracy (%)':<25} {single.accuracy:>20.2f} {multi.accuracy:>20.2f}")
    print(f"{'Avg Latency (ms)':<25} {single.avg_latency_ms:>20.2f} {multi.avg_latency_ms:>20.2f}")
    print(f"{'P95 Latency (ms)':<25} {single.p95_latency_ms:>20.2f} {multi.p95_latency_ms:>20.2f}")
    print(f"{'P99 Latency (ms)':<25} {single.p99_latency_ms:>20.2f} {multi.p99_latency_ms:>20.2f}")
    print(f"{'Avg Inference Time (ms)':<25} {single.avg_inference_time_ms:>20.2f} {multi.avg_inference_time_ms:>20.2f}")
    print(f"{'Avg Confidence (%)':<25} {single.avg_confidence:>20.2f} {multi.avg_confidence:>20.2f}")
    print(f"{'Min Confidence (%)':<25} {single.min_confidence:>20.2f} {multi.min_confidence:>20.2f}")
    print("-" * 70)
    print(f"{'SPEEDUP':<25} {speedup:>41.2f}x")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='Benchmark Kafka ML Inference Pipeline')
    parser.add_argument('--mode', choices=['single', 'multi', 'compare'], 
                       default='compare', help='Benchmark mode')
    parser.add_argument('--duration', type=int, default=60, 
                       help='Benchmark duration in seconds')
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("KAFKA ML INFERENCE PIPELINE - BENCHMARK")
    print("=" * 60)
    print(f"Mode: {args.mode}")
    print(f"Duration: {args.duration} seconds per benchmark")
    print(f"Batch Size: {BATCH_SIZE}")
    print(f"Device: {'CUDA' if torch.cuda.is_available() else 'CPU'}")
    print("=" * 60 + "\n")
    print("⚠️  Ensure the producer is running: docker-compose up producer")
    print("")
    
    if args.mode == 'single':
        metrics = benchmark_single_threaded(args.duration)
        metrics.print_report()
        
    elif args.mode == 'multi':
        metrics = benchmark_multi_process(args.duration)
        metrics.print_report()
        
    elif args.mode == 'compare':
        print("Running single-threaded benchmark first...")
        single_metrics = benchmark_single_threaded(args.duration)
        single_metrics.print_report()
        
        print("\nWaiting 5 seconds before multi-process benchmark...\n")
        time.sleep(5)
        
        print("Running multi-process benchmark...")
        multi_metrics = benchmark_multi_process(args.duration)
        multi_metrics.print_report()
        
        print_comparison(single_metrics, multi_metrics)


if __name__ == '__main__':
    main()