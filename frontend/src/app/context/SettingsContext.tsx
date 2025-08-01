// SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

"use client";

import { createContext, useContext, useState, ReactNode } from "react";

export interface MetadataField {
  name: string;
  type: "string" | "datetime";
  optional?: boolean;
}

interface SettingsContextType {
  temperature: number;
  topP: number;
  vdbTopK: number;
  rerankerTopK: number;
  confidenceScoreThreshold: number;
  useGuardrails: boolean;
  includeCitations: boolean;
  metadataSchema: MetadataField[];
  setMetadataSchema: (schema: MetadataField[]) => void;
  setTemperature: (value: number) => void;
  setTopP: (value: number) => void;
  setVdbTopK: (value: number) => void;
  setRerankerTopK: (value: number) => void;
  setConfidenceScoreThreshold: (value: number) => void;
  setUseGuardrails: (value: boolean) => void;
  setIncludeCitations: (value: boolean) => void;
}

const MIN_TEMPERATURE = 0.1;
const MIN_TOP_P = 0.1;
const DEFAULT_VDB_TOPK = 100;
const DEFAULT_RERANKER_TOPK = 10;
const DEFAULT_CONFIDENCE_THRESHOLD = 0.0;
const MIN_CONFIDENCE_THRESHOLD = 0.0;
const MAX_CONFIDENCE_THRESHOLD = 1.0;

const SettingsContext = createContext<SettingsContextType | undefined>(
  undefined
);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [temperature, setTemperatureState] = useState(0.5);
  const [topP, setTopPState] = useState(0.9);
  const [vdbTopK, setVdbTopKState] = useState(DEFAULT_VDB_TOPK);
  const [rerankerTopK, setRerankerTopKState] = useState(DEFAULT_RERANKER_TOPK);
  const [confidenceScoreThreshold, setConfidenceScoreThresholdState] = useState(DEFAULT_CONFIDENCE_THRESHOLD);
  const [useGuardrails, setUseGuardrails] = useState(false);
  const [includeCitations, setIncludeCitations] = useState(true);
  const [metadataSchema, setMetadataSchema] = useState<MetadataField[]>([]);

  const setTemperature = (value: number) => {
    setTemperatureState(Math.max(MIN_TEMPERATURE, value));
  };

  const setTopP = (value: number) => {
    setTopPState(Math.max(MIN_TOP_P, value));
  };

  // VDB topK must be >= rerankerTopK
  const setVdbTopK = (value: number) => {
    const newValue = Math.max(1, value);
    setVdbTopKState(Math.max(newValue, rerankerTopK));
  };

  // Reranker topK must be <= vdbTopK
  const setRerankerTopK = (value: number) => {
    const newValue = Math.max(1, value);
    setRerankerTopKState(Math.min(newValue, vdbTopK));
  };

  const setConfidenceScoreThreshold = (value: number) => {
    // Ensure the value is within 0-1 range
    const newValue = Math.max(MIN_CONFIDENCE_THRESHOLD, Math.min(MAX_CONFIDENCE_THRESHOLD, value));
    setConfidenceScoreThresholdState(newValue);
  };

  return (
    <SettingsContext.Provider
      value={{
        temperature,
        topP,
        vdbTopK,
        rerankerTopK,
        confidenceScoreThreshold,
        useGuardrails,
        includeCitations,
        metadataSchema,
        setMetadataSchema,
        setTemperature,
        setTopP,
        setVdbTopK,
        setRerankerTopK,
        setConfidenceScoreThreshold,
        setUseGuardrails,
        setIncludeCitations,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (context === undefined) {
    throw new Error("useSettings must be used within a SettingsProvider");
  }
  return context;
}
