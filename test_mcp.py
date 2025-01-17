import asyncio
import os
from pathlib import Path
from typing import Dict, Any

from src.dify_mcp_server.server import (
    DifyAPI,
    Server,
    InitializationOptions,
    NotificationOptions,
)
import mcp.types as types


# Initialize server and API
def init_server():
    """Initialize the server and API with proper configuration"""
    # Find config.yaml in the current directory or parent directories
    current_dir = Path.cwd()
    config_path = None

    # Search for config.yaml in current and parent directories
    search_dirs = [current_dir] + list(current_dir.parents)
    for directory in search_dirs:
        potential_config = directory / "config.yaml"
        if potential_config.exists():
            config_path = str(potential_config)
            break

    if not config_path:
        raise ValueError("config.yaml not found in current or parent directories")

    print(f"Using config file: {config_path}")

    # Set environment variable for the server
    os.environ["CONFIG_PATH"] = config_path

    # Initialize server
    server = Server("dify_mcp_server")
    dify_api = DifyAPI(config_path)

    return server, dify_api


# Initialize server and API globally
server, dify_api = init_server()


async def test_tool_listing():
    """Test listing of available tools"""
    print("\n=== Testing Tool Listing ===")
    tools = []

    # Get tools using the same logic as handle_list_tools
    print("Listing available tools...")

    for i, app_info in enumerate(dify_api.dify_app_infos):
        try:
            app_param = dify_api.dify_app_params[i]
            app_type = app_info.get("type", "unknown")

            print(f"Processing {app_info['name']} ({app_type})")

            # Create input schema
            inputSchema = dict(
                type="object",
                properties={},
                required=[],
            )

            if "user_input_form" in app_param:
                for param in app_param["user_input_form"]:
                    param_type = list(param.keys())[0]
                    param_info = param[param_type]
                    property_name = param_info["variable"]

                    param_schema = {
                        "type": param_type,
                        "description": param_info.get("label", ""),
                    }

                    if param_type == "select" and "options" in param_info:
                        param_schema["enum"] = [
                            opt["value"] for opt in param_info["options"]
                        ]
                        options_desc = ", ".join(
                            [f"{opt['display']}" for opt in param_info["options"]]
                        )
                        param_schema["description"] = (
                            f"{param_schema['description']}. Options: {options_desc}"
                        )

                    inputSchema["properties"][property_name] = param_schema

                    if param_info.get("required", False):
                        inputSchema["required"].append(property_name)

            tool = types.Tool(
                name=app_info["name"],
                description=f"{app_info.get('description', 'No description available')} ({app_type})",
                inputSchema=inputSchema,
            )
            tools.append(tool)
            print(f"Successfully added tool: {app_info['name']}")

        except Exception as e:
            print(f"Error processing tool {app_info['name']}: {str(e)}")
            continue

    assert len(tools) > 0, "No tools found"

    print(f"\nFound {len(tools)} tools:")
    for tool in tools:
        print(f"\nTool: {tool.name}")
        print(f"Description: {tool.description}")
        print("Parameters:")
        for param_name, param_info in tool.inputSchema.get("properties", {}).items():
            print(f"  - {param_name}: {param_info.get('description', '')}")
            if "enum" in param_info:
                print(f"    Options: {', '.join(param_info['enum'])}")

    return tools


async def test_football_agent():
    """Test Football Intelligence Agent"""
    print("\n=== Testing Football Intelligence Agent ===")

    # First get the tool info to see available options
    tools = await test_tool_listing()
    football_tool = next((t for t in tools if "Football" in t.name), None)

    if not football_tool:
        print("Football Intelligence Agent not found in tools")
        return False

    # Get valid options from the tool schema
    valid_query_types = (
        football_tool.inputSchema["properties"].get("query_type", {}).get("enum", [])
    )

    # Test parameters that should work
    test_params = {
        "league": "Premier League",
        "entity": "Manchester United",
        "query_type": valid_query_types[0] if valid_query_types else "Team Information",
        "time_frame": "Last 5 Matches",
    }

    print(f"Testing with parameters: {test_params}")

    try:
        # Set the current app to the football agent
        app_index = next(
            (
                i
                for i, info in enumerate(dify_api.dify_app_infos)
                if "Football" in info["name"]
            ),
            None,
        )
        if app_index is not None:
            dify_api.set_current_app(app_index)

            # Get responses
            responses = dify_api.chat_message(
                inputs=test_params, response_mode="streaming"
            )
            print("\nResponse received:")
            for res in responses:
                if (
                    "event" in res
                    and res["event"] == "agent_message"
                    and "answer" in res
                ):
                    print(res["answer"])
            return True
    except Exception as e:
        print(f"Error testing Football Agent: {str(e)}")
        return False


async def test_travel_consultant():
    """Test Travel Consultant"""
    print("\n=== Testing Travel Consultant UK ===")

    # Test parameters that should work
    test_params = {"destination": "London", "num_day": "5", "budget": "1000"}

    print(f"Testing with parameters: {test_params}")

    try:
        # Set the current app to the travel consultant
        app_index = next(
            (
                i
                for i, info in enumerate(dify_api.dify_app_infos)
                if "Travel" in info["name"]
            ),
            None,
        )
        if app_index is not None:
            dify_api.set_current_app(app_index)

            # Get responses
            responses = dify_api.chat_message(
                inputs=test_params, response_mode="streaming"
            )
            print("\nResponse received:")
            for res in responses:
                if (
                    "event" in res
                    and res["event"] == "agent_message"
                    and "answer" in res
                ):
                    print(res["answer"])
            return True
    except Exception as e:
        print(f"Error testing Travel Consultant: {str(e)}")
        return False


async def main():
    """Main test function"""
    print("Starting MCP Tool Tests...")

    # First test tool listing
    await test_tool_listing()

    # Test each tool
    football_result = await test_football_agent()
    travel_result = await test_travel_consultant()

    # Print summary
    print("\n=== Test Summary ===")
    print(f"Football Agent Test: {'PASSED' if football_result else 'FAILED'}")
    print(f"Travel Consultant Test: {'PASSED' if travel_result else 'FAILED'}")


if __name__ == "__main__":
    asyncio.run(main())
