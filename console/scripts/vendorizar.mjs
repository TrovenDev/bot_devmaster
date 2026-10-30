// Copia o bundle de navegador do supabase-js para public/vendor (o painel não usa CDN: a CSP só aceita 'self').
// Rode `npm run vendorizar` depois de atualizar a dependência.
import { copyFileSync } from "node:fs";
copyFileSync("node_modules/@supabase/supabase-js/dist/umd/supabase.js", "public/vendor/supabase.js");
console.log("public/vendor/supabase.js atualizado");
