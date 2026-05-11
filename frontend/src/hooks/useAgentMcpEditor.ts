import { useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { McpConnectionResult, McpServerEntry } from '../types/api';
import { testMcpConnections } from '../api/client';
import type { AgentBuilderFormState } from './useAgentBuilderForm';

export function useAgentMcpEditor(setForm: Dispatch<SetStateAction<AgentBuilderFormState>>) {
  const [newMcpName, setNewMcpName] = useState('');
  const [newMcpUrl, setNewMcpUrl] = useState('');
  const [newMcpAuth, setNewMcpAuth] = useState(false);
  const [newMcpAuthScope, setNewMcpAuthScope] = useState('');
  const [mcpTestResults, setMcpTestResults] = useState<Record<string, McpConnectionResult>>({});
  const [mcpTesting, setMcpTesting] = useState(false);

  const resetMcpEditor = () => {
    setNewMcpName('');
    setNewMcpUrl('');
    setNewMcpAuth(false);
    setNewMcpAuthScope('');
    setMcpTestResults({});
  };

  const addMcpServer = () => {
    if (!newMcpName.trim() || !newMcpUrl.trim()) return;
    setForm((prev) => ({
      ...prev,
      mcpServers: [...prev.mcpServers, {
        name: newMcpName.trim(),
        transport: 'http' as const,
        url: newMcpUrl.trim(),
        ...(newMcpAuth ? { authenticated: true } : {}),
        ...(newMcpAuthScope.trim() ? { authScope: newMcpAuthScope.trim() } : {}),
      }],
    }));
    setNewMcpName('');
    setNewMcpUrl('');
    setNewMcpAuth(false);
    setNewMcpAuthScope('');
  };

  const removeMcpServer = (server: McpServerEntry, index: number) => {
    setForm((prev) => ({
      ...prev,
      mcpServers: prev.mcpServers.filter((_, idx) => idx !== index),
    }));
    setMcpTestResults((prev) => {
      const next = { ...prev };
      delete next[server.name];
      return next;
    });
  };

  const testConnections = async (servers: McpServerEntry[]) => {
    if (servers.length === 0) return;
    setMcpTesting(true);
    setMcpTestResults({});
    try {
      const results = await testMcpConnections(servers);
      const map: Record<string, McpConnectionResult> = {};
      for (const result of results) {
        map[result.name] = result;
      }
      setMcpTestResults(map);
    } catch {
      // Error already shown via toast by client.ts.
    } finally {
      setMcpTesting(false);
    }
  };

  return {
    addMcpServer,
    mcpTesting,
    mcpTestResults,
    newMcpAuth,
    newMcpAuthScope,
    newMcpName,
    newMcpUrl,
    removeMcpServer,
    resetMcpEditor,
    setNewMcpAuth,
    setNewMcpAuthScope,
    setNewMcpName,
    setNewMcpUrl,
    testConnections,
  } as const;
}