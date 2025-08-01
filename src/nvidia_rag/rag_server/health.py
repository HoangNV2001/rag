# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""This defines the health check for the services used by the rag-server.
1. check_service_health(): Check the health of a service endpoint asynchronously.
2. check_minio_health(): Check the health of the MinIO server.
3. check_milvus_health(): Check the health of the Milvus database.
4. check_all_services_health(): Check the health of all services used by the application.
5. print_health_report(): Print the health report for the services used by the application.
6. check_and_print_services_health(): Check the health of all services and print a report.
"""

import time
import aiohttp
import asyncio
import os
import logging
from typing import Dict, Optional, List, Any
from pymilvus import connections, utility
from urllib.parse import urlparse

from nvidia_rag.utils.minio_operator import MinioOperator
from nvidia_rag.utils.common import get_config

logger = logging.getLogger(__name__)

async def check_service_health(
    url: str,
    service_name: str,
    method: str = "GET",
    timeout: int = 5,
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Check health of a service endpoint asynchronously.

    Args:
        url: The endpoint URL to check
        service_name: Name of the service for reporting
        method: HTTP method to use (GET, POST, etc.)
        timeout: Request timeout in seconds
        headers: Optional HTTP headers
        json_data: Optional JSON payload for POST requests

    Returns:
        Dictionary with status information
    """
    start_time = time.time()
    status = {
        "service": service_name,
        "url": url,
        "status": "unknown",
        "latency_ms": 0,
        "error": None
    }

    if not url:
        status["status"] = "skipped"
        status["error"] = "No URL provided"
        return status

    try:
        # Add scheme if missing
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url

        async with aiohttp.ClientSession() as session:
            request_kwargs = {
                "timeout": aiohttp.ClientTimeout(total=timeout),
                "headers": headers or {}
            }

            if method.upper() == "POST" and json_data:
                request_kwargs["json"] = json_data

            async with getattr(session, method.lower())(url, **request_kwargs) as response:
                status["status"] = "healthy" if response.status < 400 else "unhealthy"
                status["http_status"] = response.status
                status["latency_ms"] = round((time.time() - start_time) * 1000, 2)

    except asyncio.TimeoutError:
        status["status"] = "timeout"
        status["error"] = f"Request timed out after {timeout}s"
    except aiohttp.ClientError as e:
        status["status"] = "error"
        status["error"] = str(e)
    except Exception as e:
        status["status"] = "error"
        status["error"] = str(e)

    return status

async def check_minio_health(endpoint: str, access_key: str, secret_key: str) -> Dict[str, Any]:
    """Check MinIO server health"""
    status = {
        "service": "MinIO",
        "url": endpoint,
        "status": "unknown",
        "error": None
    }

    if not endpoint:
        status["status"] = "skipped"
        status["error"] = "No endpoint provided"
        return status

    try:
        start_time = time.time()
        minio_operator = MinioOperator(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key
        )
        # Test basic operation - list buckets
        buckets = minio_operator.client.list_buckets()
        status["status"] = "healthy"
        status["latency_ms"] = round((time.time() - start_time) * 1000, 2)
        status["buckets"] = len(buckets)
    except Exception as e:
        status["status"] = "error"
        status["error"] = str(e)

    return status

async def check_milvus_health(url: str) -> Dict[str, Any]:
    """Check Milvus database health"""
    status = {
        "service": "Milvus",
        "url": url,
        "status": "unknown",
        "error": None
    }

    if not url:
        status["status"] = "skipped"
        status["error"] = "No URL provided"
        return status

    try:
        start_time = time.time()
        parsed_url = urlparse(url)
        connection_alias = f"health_check_{parsed_url.hostname}_{parsed_url.port}_{int(time.time())}"

        # Connect to Milvus
        connections.connect(
            connection_alias,
            host=parsed_url.hostname,
            port=parsed_url.port
        )

        # Test basic operation - list collections
        collections = utility.list_collections(using=connection_alias)

        # Disconnect
        connections.disconnect(connection_alias)

        status["status"] = "healthy"
        status["latency_ms"] = round((time.time() - start_time) * 1000, 2)
        status["collections"] = len(collections)
    except Exception as e:
        status["status"] = "error"
        status["error"] = str(e)

    return status

def is_nvidia_api_catalog_url(url: str) -> bool:
    """Check if the URL is from NVIDIA API Catalog"""
    if not url:
        return True
    return any(url.startswith(prefix) for prefix in [
        "https://integrate.api.nvidia.com",
        "https://ai.api.nvidia.com",
        "https://api.nvcf.nvidia.com"
    ])

async def check_all_services_health() -> Dict[str, List[Dict[str, Any]]]:
    """
    Check health of all services used by the application

    Returns:
        Dictionary with service categories and their health status
    """
    config = get_config()

    # Create tasks for different service types
    tasks = []
    results = {
        "databases": [],
        "object_storage": [],
        "nim": [],  # New unified category for NIM services
    }

    # MinIO health check
    minio_endpoint = config.minio.endpoint
    minio_access_key = config.minio.access_key
    minio_secret_key = config.minio.secret_key
    if minio_endpoint:
        tasks.append(("object_storage", check_minio_health(
            endpoint=minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key
        )))

    # Vector DB (Milvus) health check
    if config.vector_store.url:
        tasks.append(("databases", check_milvus_health(config.vector_store.url)))

    # LLM service health check
    if config.llm.server_url and not is_nvidia_api_catalog_url(config.llm.server_url):
        llm_url = config.llm.server_url
        if not llm_url.startswith(('http://', 'https://')):
            llm_url = f"http://{llm_url}/v1/health/ready"
        else:
            llm_url = f"{llm_url}/v1/health/ready"
        tasks.append(("nim", check_service_health(
            url=llm_url,
            service_name=f"LLM ({config.llm.model_name})"
        )))
    else:
        # When URL is empty or from API catalog, assume the service is running via API catalog
        results["nim"].append({
            "service": f"LLM ({config.llm.model_name})",
            "url": "NVIDIA API Catalog",
            "status": "healthy",
            "latency_ms": 0,
            "message": "Using NVIDIA API Catalog"
        })

    query_rewriter_enabled = config.query_rewriter.enable_query_rewriter

    if query_rewriter_enabled:
        # Query rewriter LLM health check
        if config.query_rewriter.server_url and not is_nvidia_api_catalog_url(config.query_rewriter.server_url):
            qr_url = config.query_rewriter.server_url
            if not qr_url.startswith(('http://', 'https://')):
                qr_url = f"http://{qr_url}/v1/health/ready"
            else:
                qr_url = f"{qr_url}/v1/health/ready"
            tasks.append(("nim", check_service_health(
                url=qr_url,
                service_name=f"Query Rewriter ({config.query_rewriter.model_name})"
            )))
        else:
            # When URL is empty or from API catalog, assume the service is running via API catalog
            results["nim"].append({
                "service": f"Query Rewriter ({config.query_rewriter.model_name})",
                "url": "NVIDIA API Catalog",
                "status": "healthy",
                "latency_ms": 0,
                "message": "Using NVIDIA API Catalog"
            })

    # Embedding service health check
    if config.embeddings.server_url and not is_nvidia_api_catalog_url(config.embeddings.server_url):
        embed_url = config.embeddings.server_url
        if not embed_url.startswith(('http://', 'https://')):
            embed_url = f"http://{embed_url}/v1/health/ready"
        else:
            embed_url = f"{embed_url}/v1/health/ready"
        tasks.append(("nim", check_service_health(
            url=embed_url,
            service_name=f"Embeddings ({config.embeddings.model_name})"
        )))
    else:
        # When URL is empty or from API catalog, assume the service is running via API catalog
        results["nim"].append({
            "service": f"Embeddings ({config.embeddings.model_name})",
            "url": "NVIDIA API Catalog",
            "status": "healthy",
            "latency_ms": 0,
            "message": "Using NVIDIA API Catalog"
        })

    enable_reranker = config.ranking.enable_reranker
    # Ranking service health check
    if enable_reranker:
        if config.ranking.server_url and not is_nvidia_api_catalog_url(config.ranking.server_url):
            ranking_url = config.ranking.server_url
            if not ranking_url.startswith(('http://', 'https://')):
                ranking_url = f"http://{ranking_url}/v1/health/ready"
            else:
                ranking_url = f"{ranking_url}/v1/health/ready"
            tasks.append(("nim", check_service_health(
                url=ranking_url,
                service_name=f"Ranking ({config.ranking.model_name})"
            )))
        else:
            # When URL is empty or from API catalog, assume the service is running via API catalog
            results["nim"].append({
                "service": f"Ranking ({config.ranking.model_name})",
                "url": "NVIDIA API Catalog",
                "status": "healthy",
                "latency_ms": 0,
                "message": "Using NVIDIA API Catalog"
            })

    # NemoGuardrails health check
    enable_guardrails = config.enable_guardrails
    if enable_guardrails:
        guardrails_url = os.getenv('NEMO_GUARDRAILS_URL', '')
        if guardrails_url:
            if not guardrails_url.startswith(('http://', 'https://')):
                guardrails_url = f"http://{guardrails_url}/v1/health"
            else:
                guardrails_url = f"{guardrails_url}/v1/health"
            tasks.append(("nim", check_service_health(
                url=guardrails_url,
                service_name="NemoGuardrails"
            )))
        else:
            results["nim"].append({
                "service": "NemoGuardrails",
                "url": "Not configured",
                "status": "skipped",
                "message": "URL not provided"
            })

    # Reflection LLM health check
    enable_reflection = os.getenv('ENABLE_REFLECTION', 'False').lower() == 'true'
    if enable_reflection:
        reflection_llm = os.getenv('REFLECTION_LLM', '').strip('"').strip("'")
        reflection_url = os.getenv('REFLECTION_LLM_SERVERURL', '').strip('"').strip("'")
        if reflection_url:
            if not reflection_url.startswith(('http://', 'https://')):
                reflection_url = f"http://{reflection_url}/v1/health/ready"
            else:
                reflection_url = f"{reflection_url}/v1/health/ready"
            tasks.append(("nim", check_service_health(
                url=reflection_url,
                service_name=f"Reflection LLM ({reflection_llm})"
            )))
        else:
            # When URL is empty, assume the service is running via API catalog
            results["nim"].append({
                "service": f"Reflection LLM ({reflection_llm})",
                "url": "NVIDIA API Catalog",
                "status": "healthy",
                "latency_ms": 0,
                "message": "Using NVIDIA API Catalog"
            })

    # Execute all health checks concurrently
    for category, task in tasks:
        result = await task
        results[category].append(result)

    return results

def print_health_report(health_results: Dict[str, List[Dict[str, Any]]]) -> None:
    """
    Print health status for individual services

    Args:
        health_results: Results from check_all_services_health
    """
    logger.info("===== SERVICE HEALTH STATUS =====")

    for category, services in health_results.items():
        if not services or type(services) == str:
            continue

        for service in services:
            if service["status"] == "healthy":
                logger.info(f"Service '{service['service']}' is healthy - Response time: {service.get('latency_ms', 'N/A')}ms")
            elif service["status"] == "skipped":
                logger.info(f"Service '{service['service']}' check skipped - Reason: {service.get('error', 'No URL provided')}")
            else:
                error_msg = service.get("error", "Unknown error")
                logger.info(f"Service '{service['service']}' is not healthy - Issue: {error_msg}")

    logger.info("================================")

async def check_and_print_services_health():
    """
    Check health of all services and print a report
    """
    health_results = await check_all_services_health()
    print_health_report(health_results)
    return health_results

def check_services_health():
    """
    Synchronous wrapper for checking service health
    """
    return asyncio.run(check_and_print_services_health())
