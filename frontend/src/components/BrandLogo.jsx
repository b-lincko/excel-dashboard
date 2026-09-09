export default function BrandLogo({ className = "h-10 w-auto max-w-[180px] object-contain", alt = "Linkco" }) {
  return (
    <img
      src="/linkco-logo.png"
      alt={alt}
      className={`bg-black ${className}`}
    />
  );
}
