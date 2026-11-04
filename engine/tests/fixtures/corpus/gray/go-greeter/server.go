package main

import (
	"context"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

type GreetInput struct {
	Name string `json:"name"`
}

type GreetOutput struct {
	Text string `json:"text"`
}

func greet(ctx context.Context, req *mcp.CallToolRequest, in GreetInput) (*mcp.CallToolResult, GreetOutput, error) {
	return nil, GreetOutput{Text: "Hello, " + in.Name}, nil
}

func build() *mcp.Server {
	server := mcp.NewServer(&mcp.Implementation{Name: "greeter", Version: "1.0.0"}, nil)
	mcp.AddTool(server, &mcp.Tool{Name: "greet", Description: "Say hello to someone"}, greet)
	return server
}
