/**
 * Where screenshots are read from (run 4, J6): local disk in development, an S3-compatible bucket
 * (MinIO, S3, R2) in production. The file route checks access first; with S3 it then redirects
 * to a presigned GET link that expires after a few minutes, so the bucket stays private and the
 * web app never streams image bytes. Presigning is a local computation: no request to the store.
 */
import { GetObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

export type StorageConfig =
  | { mode: "local" }
  | { mode: "s3"; bucket: string; region: string; endpoint: string | null; publicEndpoint: string | null; accessKey: string; secretKey: string };

export const LINK_SECONDS = 300;

export function storageConfig(env: Record<string, string | undefined> = process.env): StorageConfig {
  if (env.STORAGE !== "s3") return { mode: "local" };
  return {
    mode: "s3",
    bucket: env.S3_BUCKET ?? "screenshots",
    region: env.S3_REGION ?? "us-east-1",
    endpoint: env.S3_ENDPOINT || null,
    // The store's address as the browser reaches it (inside Docker the app uses minio:9000).
    publicEndpoint: env.S3_PUBLIC_ENDPOINT || env.S3_ENDPOINT || null,
    accessKey: env.S3_ACCESS_KEY ?? "",
    secretKey: env.S3_SECRET_KEY ?? "",
  };
}

export async function presignedUrl(config: Extract<StorageConfig, { mode: "s3" }>, key: string, seconds = LINK_SECONDS): Promise<string> {
  const client = new S3Client({
    region: config.region,
    endpoint: config.publicEndpoint ?? undefined,
    forcePathStyle: Boolean(config.publicEndpoint), // MinIO serves buckets as paths
    credentials: { accessKeyId: config.accessKey, secretAccessKey: config.secretKey },
  });
  return getSignedUrl(client, new GetObjectCommand({ Bucket: config.bucket, Key: key }), { expiresIn: seconds });
}
