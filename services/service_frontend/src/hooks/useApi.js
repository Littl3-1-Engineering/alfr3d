import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { API_BASE_URL } from '../config';

export const useRoutines = () => {
  return useQuery({
    queryKey: ['routines'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE_URL}/api/routines`);
      if (!response.ok) throw new Error('Failed to fetch routines');
      return response.json();
    }
  });
};

export const useCreateRoutine = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (routine) => {
      const response = await fetch(`${API_BASE_URL}/api/routines`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(routine)
      });
      if (!response.ok) throw new Error('Failed to create routine');
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['routines'] });
    }
  });
};

export const useUpdateRoutine = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...routine }) => {
      const response = await fetch(`${API_BASE_URL}/api/routines/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(routine)
      });
      if (!response.ok) throw new Error('Failed to update routine');
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['routines'] });
    }
  });
};

export const useDeleteRoutine = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id) => {
      const response = await fetch(`${API_BASE_URL}/api/routines/${id}`, {
        method: 'DELETE'
      });
      if (!response.ok) throw new Error('Failed to delete routine');
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['routines'] });
    }
  });
};

export const usePersonality = () => {
  return useQuery({
    queryKey: ['personality'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE_URL}/api/personality`);
      if (!response.ok) throw new Error('Failed to fetch personality');
      return response.json();
    }
  });
};

export const usePersonalityPresets = () => {
  return useQuery({
    queryKey: ['personality', 'presets'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE_URL}/api/personality/presets`);
      if (!response.ok) throw new Error('Failed to fetch presets');
      return response.json();
    }
  });
};

export const useLlmConfig = () => {
  return useQuery({
    queryKey: ['llm-config'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE_URL}/api/personality/llm-config`);
      if (!response.ok) throw new Error('Failed to fetch LLM config');
      return response.json();
    }
  });
};

export const useUpdatePersonality = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (personality) => {
      const response = await fetch(`${API_BASE_URL}/api/personality`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(personality)
      });
      if (!response.ok) throw new Error('Failed to update personality');
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['personality'] });
    }
  });
};

export const useQuips = () => {
  return useQuery({
    queryKey: ['quips'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE_URL}/api/quips`);
      if (!response.ok) throw new Error('Failed to fetch quips');
      return response.json();
    }
  });
};

export const useCreateQuip = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (quip) => {
      const response = await fetch(`${API_BASE_URL}/api/quips`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(quip)
      });
      if (!response.ok) throw new Error('Failed to create quip');
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quips'] });
    }
  });
};

export const useUpdateQuip = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...quip }) => {
      const response = await fetch(`${API_BASE_URL}/api/quips/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(quip)
      });
      if (!response.ok) throw new Error('Failed to update quip');
      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quips'] });
    }
  });
};

export const useDeleteQuip = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id) => {
      const response = await fetch(`${API_BASE_URL}/api/quips/${id}`, {
        method: 'DELETE'
      });
      if (!response.ok) throw new Error('Failed to delete quip');
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['quips'] });
    }
  });
};

export const useIntegrationStatus = () => {
  return useQuery({
    queryKey: ['integrations'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE_URL}/api/integrations/status`);
      if (!response.ok) throw new Error('Failed to fetch integration status');
      return response.json();
    }
  });
};

export const useIotStatus = () => {
  return useQuery({
    queryKey: ['iot-status'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE_URL}/api/iot/status`);
      if (!response.ok) throw new Error('Failed to fetch IoT status');
      return response.json();
    }
  });
};
