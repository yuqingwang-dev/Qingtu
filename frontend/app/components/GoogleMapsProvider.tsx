"use client";

import { LoadScript } from "@react-google-maps/api";

const libraries: ("places")[] = ["places"];
const googleMapsApiKey = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY || "";

export default function GoogleMapsProvider({ children }: { children: React.ReactNode }) {
  if (!googleMapsApiKey) {
    return <>{children}</>;
  }

  return (
    <LoadScript
      googleMapsApiKey={googleMapsApiKey}
      libraries={libraries}
      loadingElement={<></>}
    >
      {children}
    </LoadScript>
  );
}
