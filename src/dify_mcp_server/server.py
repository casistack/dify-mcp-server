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
        print(f"Initializing server with config path: {config_path}")
        self.config = OmegaConf.load(config_path)

        # dify configs
        self.dify_base_url = self.config.dify_base_url
        self.dify_apps = self.config.dify_apps
        self.user = user

        # Initialize collections for valid apps
        self.dify_app_infos = []
        self.dify_app_params = []
        self.dify_app_metas = []
        self._app_id_to_index = {}

        print(f"Initializing Dify API with {len(self.dify_apps)} apps")

        for idx, app in enumerate(self.dify_apps):
            try:
                # Set headers for current app
                self.headers = {
                    "Authorization": f"Bearer {app['app_sk']}",
                    "Content-Type": "application/json",
                }

                print(f"Fetching info for app {app['app_sk'][-8:]}")

                # Fetch app information
                app_info = self.get_app_info()
                app_params = self.get_app_parameters()
                app_meta = self.get_app_meta()

                # Add type information from config
                app_info["type"] = app.get("type", "unknown")

                print(
                    f"Successfully initialized {app_info['name']} ({app_info['type']})"
                )

                # Store valid app information
                self.dify_app_infos.append(app_info)
                self.dify_app_params.append(app_params)
                self.dify_app_metas.append(app_meta)

                # Create internal mapping using app SK as unique identifier
                self._app_id_to_index[app["app_sk"]] = idx

            except requests.exceptions.RequestException as e:
                print(
                    f"Warning: Failed to initialize app {app['app_sk'][-8:]}: {str(e)}"
                )
                if hasattr(e.response, "json"):
                    try:
                        error_details = e.response.json()
                        print(f"Error details: {error_details}")
                    except:
                        pass
                continue
            except Exception as e:
                print(
                    f"Unexpected error initializing app {app['app_sk'][-8:]}: {str(e)}"
                )
                continue

        if not self.dify_app_infos:
            raise ValueError("No valid apps were initialized")

        print(f"Successfully initialized {len(self.dify_app_infos)} apps")

        # Set current app to first valid app
        self.current_app_index = 0
        self._update_headers()

    def _update_headers(self):
        """Update headers with current app's API key."""
        if self.current_app_index >= len(self.dify_apps):
            raise ValueError("Invalid app index")
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
        try:
            url = f"{self.dify_base_url}/info"
            params = {"user": self.user}
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching app info: {str(e)}")
            raise

    def get_app_parameters(self) -> Dict[str, Any]:
        """Get current app parameters."""
        try:
            url = f"{self.dify_base_url}/parameters"
            params = {"user": self.user}
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching app parameters: {str(e)}")
            raise

    def get_app_meta(self) -> Dict[str, Any]:
        """Get current app meta information."""
        try:
            url = f"{self.dify_base_url}/meta"
            params = {"user": self.user}
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching app meta: {str(e)}")
            raise

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

            # Get current app info
            current_app = self.dify_apps[self.current_app_index]
            app_type = current_app.get(
                "type", "agent"
            )  # Default to agent for backward compatibility

            # Prepare request data
            data = {
                "inputs": inputs,
                "response_mode": response_mode,
                "user": user or "default-user",
            }

            # Add conversation_id for agents/chatbots
            if app_type != "workflow" and conversation_id:
                data["conversation_id"] = conversation_id

            # Add files if provided
            if files:
                data["files"] = files

            # Add query for agents/chatbots
            if app_type != "workflow":
                query = self._construct_query(inputs, app_parameters)
                data["query"] = query

            # Choose endpoint based on type
            endpoint = "/workflows/run" if app_type == "workflow" else "/chat-messages"

            # Make request to appropriate endpoint
            response = requests.post(
                f"{self.dify_base_url}{endpoint}",
                headers=self.headers,
                json=data,
                stream=response_mode == "streaming",
            )
            response.raise_for_status()

            if response_mode == "streaming":
                return self._handle_streaming_response(response, app_type)
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
        self, response: requests.Response, app_type: str = "agent"
    ) -> Generator[Dict[str, Any], None, None]:
        """Handle streaming response from Dify API."""
        for line in response.iter_lines():
            if line:
                # Remove 'data: ' prefix if present
                if line.startswith(b"data: "):
                    line = line[6:]
                try:
                    event = json.loads(line)

                    # For workflows, extract text content from various events
                    if app_type == "workflow":
                        if event.get("event") == "text_chunk" and "data" in event:
                            # Reformat as agent_message for consistency
                            yield {
                                "event": "agent_message",
                                "answer": event["data"].get("text", ""),
                            }
                        elif event.get("event") == "workflow_finished":
                            yield {"event": "message_end"}
                    else:
                        # Pass through agent/chatbot events as is
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


# Global instances
config_path = os.getenv("CONFIG_PATH")
if not config_path:
    raise ValueError("CONFIG_PATH environment variable not set")

print(f"Initializing server with config path: {config_path}")
server = Server("dify_mcp_server")
dify_api = DifyAPI(config_path)


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    tools = []

    for i, app_info in enumerate(dify_api.dify_app_infos):
        app_param = dify_api.dify_app_params[i]

        # Create input schema
        inputSchema = dict(
            type="object",
            properties={},
            required=[],
        )

        for param in app_param["user_input_form"]:
            param_type = list(param.keys())[0]
            param_info = param[param_type]
            property_name = param_info["variable"]
            inputSchema["properties"][property_name] = dict(
                type=param_type,
                description=param_info["label"],  # Use original label
            )
            if param_info.get("required", False):
                inputSchema["required"].append(property_name)

        # Create tool using only the app name for display, with whitespace trimmed
        tool = types.Tool(
            name=app_info["name"].strip(),  # Trim whitespace from name
            description=app_info.get("description", "No description available"),
            inputSchema=inputSchema,
        )
        tools.append(tool)

    return tools


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    # Find the app index by name, with whitespace trimming
    app_index = next(
        (
            i
            for i, info in enumerate(dify_api.dify_app_infos)
            if info["name"].strip() == name.strip()
        ),
        None,
    )

    if app_index is not None:
        dify_api.set_current_app(app_index)

        # Get app type
        current_app = dify_api.dify_apps[app_index]
        app_type = current_app.get(
            "type", "agent"
        )  # Default to agent for backward compatibility

        # Use streaming for agents, blocking for workflows
        response_mode = "blocking" if app_type == "workflow" else "streaming"

        # Call chat_message with the arguments
        responses = dify_api.chat_message(
            inputs=arguments or {}, response_mode=response_mode
        )

        mcp_out = []
        if response_mode == "streaming":
            for res in responses:
                if "event" in res:
                    if res["event"] == "agent_message" and "answer" in res:
                        mcp_out.append(
                            types.TextContent(type="text", text=res["answer"])
                        )
                    elif res["event"] == "message_end":
                        break
        else:
            # For blocking mode, handle the single response
            if isinstance(responses, dict):
                answer = responses.get("answer", "")
                if answer:
                    mcp_out.append(types.TextContent(type="text", text=answer))

        return mcp_out
    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    """Run the server using stdin/stdout streams"""
    print("Starting Dify MCP server...")

    try:
        # Verify API connectivity before starting server
        print("Verifying API connectivity...")
        for idx, app in enumerate(dify_api.dify_app_infos):
            print(f"Found tool: {app['name']} ({app.get('type', 'unknown')})")

        print(f"Successfully verified {len(dify_api.dify_app_infos)} tools")

        # Start server
        print("Starting MCP server...")
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
    except Exception as e:
        print(f"Server error: {str(e)}")
        if hasattr(e, "__context__"):
            print(f"Context: {str(e.__context__)}")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        raise
