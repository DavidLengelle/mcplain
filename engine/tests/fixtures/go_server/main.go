package main

import "github.com/modelcontextprotocol/go-sdk/mcp"

func main() {
	server := mcp.NewServer(&mcp.Implementation{Name: "greeter"}, nil)
	_ = server
}
