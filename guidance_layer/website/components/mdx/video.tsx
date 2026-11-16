// A video from the site's public folder. Next.js adds the base path to images
// and links, but not to a plain <video>, so it is added here the same way
// next.config.mjs decides it.
const basePath = process.env.LOCAL_PREVIEW ? '' : '/gaik-toolkit';

export function Video({
  src,
  poster,
  label,
}: {
  src: string;
  poster?: string;
  label: string;
}) {
  return (
    <video
      src={`${basePath}${src}`}
      poster={poster ? `${basePath}${poster}` : undefined}
      aria-label={label}
      controls
      muted
      playsInline
      preload="metadata"
      className="my-6 aspect-video w-full rounded-lg border bg-black"
    />
  );
}
