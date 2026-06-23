# src/collector/scheduler.py
# Periodic collection scheduler
# Manages scheduled resource metric collection tasks
# Uses APScheduler for reliable scheduling

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from typing import Dict, List
from loguru import logger
from datetime import datetime

from config.settings import Settings
from src.collector.collectors import (
    CPUMetrics, 
    MemoryMetrics, 
    DiskMetrics, 
    NetworkMetrics,
    ProcessMetrics
)


class CollectionScheduler:
    """
    Scheduler for periodic resource metric collection
    Manages multiple collectors with different intervals
    Stores metrics in InfluxDB time-series database
    """
    
    def __init__(self, settings: Settings, influx_client: InfluxDBClient):
        self.settings = settings
        self.influx_client = influx_client
        self.scheduler = AsyncIOScheduler()
        
        # Initialize collectors
        self.collectors = {
            'cpu': CPUMetrics(),
            'memory': MemoryMetrics(),
            'disk': DiskMetrics(),
            'network': NetworkMetrics(),
            'process': ProcessMetrics()
        }
        
        # Collection intervals mapping
        self.intervals = {
            'cpu': settings.CPU_COLLECTION_INTERVAL,
            'memory': settings.MEMORY_COLLECTION_INTERVAL,
            'disk': settings.DISK_COLLECTION_INTERVAL,
            'network': settings.NETWORK_COLLECTION_INTERVAL,
            'process': settings.PROCESS_COLLECTION_INTERVAL
        }
    
    async def collect_and_store(self, resource_type: str):
        """
        Collect metrics for specified resource and store in InfluxDB
        """
        try:
            logger.debug(f"Starting collection for {resource_type}")
            
            # Collect metrics
            collector = self.collectors.get(resource_type)
            if not collector:
                logger.error(f"No collector found for {resource_type}")
                return
            
            metrics = collector.collect()
            
            if metrics:
                # Store in InfluxDB
                await self._store_metrics(metrics)
                logger.info(f"Stored {len(metrics)} {resource_type} metrics")
            
        except Exception as e:
            logger.error(f"Error in collection task for {resource_type}: {e}")
    
    async def _store_metrics(self, metrics: List):
        """
        Store collected metrics in InfluxDB
        Uses synchronous write API for reliability
        """
        try:
            write_api = self.influx_client.write_api(write_options=SYNCHRONOUS)
            
            for metric in metrics:
                # Convert to InfluxDB point
                point = {
                    "measurement": f"resource_{metric.resource_type}",
                    "tags": {
                        "metric_name": metric.metric_name,
                        "unit": metric.unit,
                        **metric.tags
                    },
                    "time": metric.timestamp,
                    "fields": {
                        "value": metric.value
                    }
                }
                
                write_api.write(
                    bucket=self.settings.INFLUXDB_BUCKET,
                    org=self.settings.INFLUXDB_ORG,
                    record=point
                )
            
            logger.debug("Metrics stored successfully in InfluxDB")
            
        except Exception as e:
            logger.error(f"Error storing metrics in InfluxDB: {e}")
            raise
    
    async def start(self):
        """
        Start all collection jobs
        Adds jobs to scheduler with configured intervals
        """
        logger.info("Starting collection scheduler...")
        
        for resource_type, interval in self.intervals.items():
            self.scheduler.add_job(
                self.collect_and_store,
                trigger=IntervalTrigger(seconds=interval),
                args=[resource_type],
                id=f"collect_{resource_type}",
                name=f"Collect {resource_type} metrics",
                replace_existing=True,
                max_instances=1  # Prevent overlapping executions
            )
            logger.info(f"Scheduled {resource_type} collection every {interval}s")
        
        self.scheduler.start()
        logger.info("Collection scheduler started successfully")
    
    async def stop(self):
        """
        Stop all collection jobs
        Gracefully shuts down the scheduler
        """
        logger.info("Stopping collection scheduler...")
        self.scheduler.shutdown(wait=True)
        logger.info("Collection scheduler stopped")
    
    async def trigger_manual_collection(self, resource_type: str = None):
        """
        Trigger manual collection for specified resource or all resources
        """
        if resource_type and resource_type in self.collectors:
            await self.collect_and_store(resource_type)
        else:
            for resource in self.collectors.keys():
                await self.collect_and_store(resource)
