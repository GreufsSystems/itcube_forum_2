import os
import time
import requests
from typing import List, Dict, Any, Optional
from flask import current_app
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

class DeepSeekAPIError(Exception):
    """Custom exception for DeepSeek API errors"""
    pass

class DeepSeekAPI:
    def __init__(self, 
                 api_key: Optional[str] = None,
                 base_url: str = "https://api.deepseek.com/v1",
                 model: str = "deepseek-chat",
                 temperature: float = 0.7,
                 max_tokens: int = 1000,
                 timeout: int = 30,
                 max_retries: int = 3,
                 retry_delay: float = 1.0):
        """
        Initialize DeepSeek API client
        
        Args:
            api_key: API key for DeepSeek. If None, will try to get from environment
            base_url: Base URL for API requests
            model: Model to use for completions
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens in response
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries on failure
            retry_delay: Delay between retries in seconds
        """
        # Try to get API key from environment variables
        self.api_key = api_key or os.getenv('DEEPSEEK_API_KEY')
        logger.info(f"API Key found: {'Yes' if self.api_key else 'No'}")
        
        if not self.api_key:
            error_msg = "No API key provided. Set DEEPSEEK_API_KEY environment variable."
            logger.error(error_msg)
            raise DeepSeekAPIError(error_msg)
            
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        logger.info("DeepSeek API client initialized successfully")

    def _make_request(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Helper method to make API requests"""
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_msg = f"API request failed: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                error_msg += f", Status: {e.response.status_code}, Response: {e.response.text}"
            raise DeepSeekAPIError(error_msg)

    def get_chat_response(self, messages: List[Dict[str, str]]) -> str:
        """
        Get chat completion from DeepSeek API
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            
        Returns:
            str: Response text from the model
            
        Raises:
            DeepSeekAPIError: If API request fails after retries
        """
        logger.info(f"Attempting to get chat response with {len(messages)} messages")
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Making API request (attempt {attempt + 1}/{self.max_retries})")
                response = self._make_request("chat/completions", payload)
                
                if not response.get("choices"):
                    raise DeepSeekAPIError("Invalid response format from API")
                
                logger.info("Successfully received response from API")
                return response["choices"][0]["message"]["content"]
                
            except DeepSeekAPIError as e:
                error_msg = f"Error in DeepSeek API (attempt {attempt + 1}/{self.max_retries}): {str(e)}"
                logger.error(error_msg)
                
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1)
                    logger.info(f"Waiting {wait_time} seconds before retry")
                    time.sleep(wait_time)
                    continue
                    
                raise DeepSeekAPIError(error_msg)

# Create singleton instance
try:
    logger.info("Initializing DeepSeek API singleton instance")
    deepseek = DeepSeekAPI()
    logger.info("DeepSeek API singleton instance created successfully")
except DeepSeekAPIError as e:
    logger.error(f"Failed to initialize DeepSeek API: {str(e)}")
    deepseek = None