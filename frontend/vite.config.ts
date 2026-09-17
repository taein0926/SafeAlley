import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteStaticCopy } from "vite-plugin-static-copy";

const cesiumBuild = "node_modules/cesium/Build/Cesium";

export default defineConfig({
  define: {
    CESIUM_BASE_URL: JSON.stringify("/cesium"),
  },
  plugins: [
    react(),
    viteStaticCopy({
      targets: [
        { src: `${cesiumBuild}/Workers`, dest: "cesium" },
        { src: `${cesiumBuild}/Assets`, dest: "cesium" },
        { src: `${cesiumBuild}/ThirdParty`, dest: "cesium" },
        { src: `${cesiumBuild}/Widgets`, dest: "cesium" },
      ],
    }),
  ],
});
