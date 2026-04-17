# Tool use

Tool use lets Claude call functions you define and feed their outputs back
into the conversation. You declare tools via the `tools` parameter, each tool
carrying a name, description, and JSON schema `input_schema`. When Claude
chooses to call a tool, the response has `stop_reason` set to `tool_use` and
includes one or more `tool_use` content blocks. Your code runs the tool and
returns the result as a `tool_result` block inside the next user message.

Claude supports parallel tool calls: a single assistant turn may emit multiple
`tool_use` blocks, all of which you execute and return together. Setting
`tool_choice` to `{"type": "any"}` forces Claude to call some tool; `{"type":
"tool", "name": "..."}` forces a specific tool. The default `{"type": "auto"}`
lets Claude decide whether to use tools at all.
