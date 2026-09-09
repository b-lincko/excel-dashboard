import { useTheme } from "../context/ThemeContext.jsx";

/**
 * Linkco wordmark with transparency. Picks the ink variant on light
 * surfaces (white artwork would vanish) and the white variant on dark ones.
 */
export default function BrandLogo({ className = "h-10 w-auto max-w-[180px] object-contain", alt = "Linkco" }) {
  const { theme } = useTheme();
  const src = theme === "dark" ? "/linkco-logo.png" : "/linkco-logo-dark.png";
  return <img src={src} alt={alt} className={className} />;
}
