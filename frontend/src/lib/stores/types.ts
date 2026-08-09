export interface CivitaiModel {
  id: number;
  name: string;
  description?: string;
  type: string;
  nsfw: boolean;
  nsfwClassificationKnown?: boolean;
  stats?: {
    downloadCount: number;
    ratingCount: number;
    rating: number;
    thumbsUpCount: number;
    thumbsDownCount: number;
    favoriteCount?: number;
    commentCount?: number;
    tippedAmountCount?: number;
  };
  creator?: { username: string; image?: string };
  modelVersions?: ModelVersion[];
  images?: ModelImage[];
  tags?: string[];
  baseModel?: string;
  cosmetic?: { cssFrame: string; glow: boolean; type?: string; color?: string; brightness?: number; textureUrl?: string; textureWidth?: number; textureHeight?: number } | null;
  poster?: string;
  baseModels?: string[];
  avatarDeco?: string;
  badge?: string;
  profileBackground?: { url: string; type: "image" | "video" };
  hasBuzz?: boolean;
  nameplate?: { gradient?: string; color?: string };
  availability?: string;
  earlyAccessDeadline?: string;
  publishedAt?: string;
  createdAt?: string;
  mode?: string;
}

export interface ModelDependency {
  type: string;
  modelId?: number;
  modelName?: string;
  versionId: number;
  versionName?: string;
  fileId?: number;
  name: string;
  sizeKB: number;
  required?: boolean;
  downloadUrl: string;
}

export interface ModelVersion {
  id: number;
  name: string;
  description?: string;
  baseModel?: string;
  baseModelType?: string;
  trainedWords?: string[];
  files?: ModelFile[];
  images?: ModelImage[];
  downloadUrl?: string;
  createdAt?: string;
  updatedAt?: string;
  dependencies?: ModelDependency[];
  availability?: string;
  earlyAccessEndsAt?: string;
  buzzCost?: number;
  allowCommercialUse?: unknown;
  allowDerivatives?: boolean;
  allowNoCredit?: boolean;
  allowDifferentLicense?: boolean;
  baseModels?: string[];
  epochs?: number;
  steps?: number;
  clipSkip?: number;
  air?: string;
  tensorType?: string;
  modelSize?: string;
  creator?: { username: string; image?: string; createdAt?: string };
}

export interface ModelFile {
  id: number;
  name: string;
  sizeKB: number;
  type: string;
  primary?: boolean;
  format?: string;
  fp?: string;
  sizeType?: string;
  downloadUrl?: string;
  hashes?: Record<string, string>;
  scannedAt?: string | null;
  pickleScanResult?: string | null;
  virusScanResult?: string | null;
}

export interface ModelImage {
  id: number;
  url: string;
  nsfw: string;
  width: number;
  height: number;
  type: string;
  nsfwLevel?: number;
  meta?: Record<string, unknown>;
}

export interface LocalModel {
  id: number;
  name: string;
  path: string;
  size: number;
  modelId?: number;
  versionId?: number;
  type: string;
  installed: boolean;
}

export interface DownloadItem {
  id: string;
  versionId: number;
  modelName: string;
  progress: number;
  status: "queued" | "downloading" | "completed" | "failed" | "cancelled";
  error?: string;
  filePath?: string;
}

export interface Filters {
  search: string;
  modelType: string[];
  baseModel: string[];
  nsfw: boolean;
  sort: string;
  period: string;
  eaOnly: boolean;
  updatedOnly: boolean;
}

export interface FrontendConfig {
  modelsRoot: string;
  dirMap: Record<string, string>;
  frontendDirMap: Record<string, string>;
}
