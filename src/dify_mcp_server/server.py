import asyncio
import json
import os
from abc import ABC
from typing import Dict, Any, Optional, List, Union, Generator

import mcp.server.stdio
import mcp.types as types
import requests
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from omegaconf import OmegaConf


class DifyAPI(ABC):
    def __init__(self, config_path, user="default_user"):
        if not config_path:
            raise ValueError("config path not provided")
        self.config = OmegaConf.load(config_path)

        # dify configs
        self.dify_base_url = self.config.dify_base_url
        self.dify_apps = self.config.dify_apps
        self.user = user

        # Set current app index
        self.current_app_index = 0

        # Initialize headers property
        self._update_headers()

        # dify app infos
        dify_app_infos = []
        dify_app_params = []
        dify_app_metas = []
        for app in self.dify_apps:
            dify_app_infos.append(self.get_app_info())
            dify_app_params.append(self.get_app_parameters())
            dify_app_metas.append(self.get_app_meta())
        self.dify_app_infos = dify_app_infos
        self.dify_app_params = dify_app_params
        self.dify_app_metas = dify_app_metas
        self.dify_app_names = [x["name"] for x in dify_app_infos]

    def _update_headers(self):
        """Update headers with current app's API key."""
        current_app = self.dify_apps[self.current_app_index]
        self.headers = {
            "Authorization": f"Bearer {current_app['app_sk']}",
            "Content-Type": "application/json",
        }

    def set_current_app(self, app_index: int):
        """Set the current app by index."""
        if 0 <= app_index < len(self.dify_apps):
            self.current_app_index = app_index
            self._update_headers()
        else:
            raise ValueError(
                f"Invalid app index: {app_index}. Must be between 0 and {len(self.dify_apps)-1}"
            )

    def get_app_info(self) -> Dict[str, Any]:
        """Get current app info."""
        url = f"{self.dify_base_url}/info"
        params = {"user": self.user}
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    def get_app_parameters(self) -> Dict[str, Any]:
        """Get current app parameters."""
        url = f"{self.dify_base_url}/parameters"
        params = {"user": self.user}
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    def get_app_meta(self) -> Dict[str, Any]:
        """Get current app meta information."""
        url = f"{self.dify_base_url}/meta"
        params = {"user": self.user}
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    def _construct_query(
        self, inputs: Dict[str, Any], app_parameters: Dict[str, Any]
    ) -> str:
        """Constructs a natural language query from the inputs and app parameters."""
        # Get parameter metadata if available
        param_metadata = app_parameters.get("parameters", {})

        # Process inputs based on parameter metadata
        processed_inputs = {}
        for key, value in inputs.items():
            param_info = param_metadata.get(key, {})
            if param_info.get("type") == "select" and "options" in param_info:
                # For select parameters, use the display value from options if available
                options = {
                    opt["value"]: opt["display"] for opt in param_info["options"]
                }
                processed_inputs[key] = options.get(value, value)
            else:
                processed_inputs[key] = value

        # Construct query parts
        query_parts = []
        if "destination" in processed_inputs:
            query_parts.append(
                f"I want to plan a trip to {processed_inputs['destination']}"
            )
        if "num_day" in processed_inputs:
            query_parts.append(f"for {processed_inputs['num_day']} days")
        if "budget" in processed_inputs:
            query_parts.append(f"with a budget {processed_inputs['budget']}")

        # Join parts with proper punctuation
        query = " ".join(query_parts) + "."
        return query

    def chat_message(
        self,
        inputs: Dict[str, Any],
        response_mode: str = "streaming",
        conversation_id: Optional[str] = None,
        user: Optional[str] = None,
        files: Optional[List[Dict[str, Any]]] = None,
    ) -> Union[Dict[str, Any], Generator[Dict[str, Any], None, None]]:
        """Send a chat message to the Dify API."""
        try:
            # Get app parameters for proper input handling
            app_parameters = self.get_app_parameters()

            # Construct the natural language query
            query = self._construct_query(inputs, app_parameters)

            # Prepare request data
            data = {
                "inputs": inputs,
                "query": query,
                "response_mode": response_mode,
                "user": user or "default-user",
            }

            if conversation_id:
                data["conversation_id"] = conversation_id

            if files:
                data["files"] = files

            # Make request to chat-messages endpoint
            response = requests.post(
                f"{self.dify_base_url}/chat-messages",
                headers=self.headers,
                json=data,
                stream=response_mode == "streaming",
            )
            response.raise_for_status()

            if response_mode == "streaming":
                return self._handle_streaming_response(response)
            else:
                return response.json()

        except requests.exceptions.RequestException as e:
            error_msg = f"Error making request to Dify API: {str(e)}"
            if hasattr(e.response, "json"):
                try:
                    error_details = e.response.json()
                    error_msg = f"{error_msg}. Details: {error_details}"
                except ValueError:
                    pass
            raise Exception(error_msg)

    def _handle_streaming_response(
        self, response: requests.Response
    ) -> Generator[Dict[str, Any], None, None]:
        """Handle streaming response from Dify API."""
        for line in response.iter_lines():
            if line:
                # Remove 'data: ' prefix if present
                if line.startswith(b"data: "):
                    line = line[6:]
                try:
                    event = json.loads(line)
                    yield event
                except json.JSONDecodeError as e:
                    print(f"Error decoding JSON from stream: {e}")
                    continue

    def upload_file(self, api_key, file_path, user="default_user"):

        url = f"{self.dify_base_url}/files/upload"
        headers = {"Authorization": f"Bearer {api_key}"}
        files = {"file": open(file_path, "rb")}
        data = {"user": user}
        response = requests.post(url, headers=headers, files=files, data=data)
        response.raise_for_status()
        return response.json()

    def stop_response(self, api_key, task_id, user="default_user"):

        url = f"{self.dify_base_url}/chat-messages/{task_id}/stop"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        data = {"user": user}
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()


config_path = os.getenv("CONFIG_PATH")
server = Server("dify_mcp_server")
dify_api = DifyAPI(config_path)


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    tools = []
    tool_names = dify_api.dify_app_names
    tool_infos = dify_api.dify_app_infos
    tool_params = dify_api.dify_app_params
    tool_num = len(tool_names)
    for i in range(tool_num):
        # 0. load app info for each tool
        app_info = tool_infos[i]
        # 1. load app param for each tool
        inputSchema = dict(
            type="object",
            properties={},
            required=[],
        )
        app_param = tool_params[i]
        property_num = len(app_param["user_input_form"])
        if property_num > 0:
            for j in range(property_num):
                param = app_param["user_input_form"][j]
                # TODO: Add readme about strange dify user input param format
                param_type = list(param.keys())[0]
                param_info = param[param_type]
                property_name = param_info["variable"]
                inputSchema["properties"][property_name] = dict(
                    type=param_type,
                    description=param_info["label"],
                )
                if param_info["required"]:
                    inputSchema["required"].append(property_name)

        tools.append(
            types.Tool(
                name=app_info["name"],
                description=app_info["description"],
                inputSchema=inputSchema,
            )
        )
    return tools


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    tool_names = dify_api.dify_app_names
    if name in tool_names:
        tool_idx = tool_names.index(name)
        dify_api.set_current_app(tool_idx)  # Set the current app

        # Call chat_message with the correct arguments
        responses = dify_api.chat_message(
            inputs=arguments or {}, response_mode="streaming"
        )

        mcp_out = []
        for res in responses:
            if "event" in res:
                if res["event"] == "agent_message" and "answer" in res:
                    mcp_out.append(types.TextContent(type="text", text=res["answer"]))
                elif res["event"] == "message_end":
                    break

        return mcp_out
    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="dify_mcp_server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
