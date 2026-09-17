declare module "react-simple-maps" {
  import type { ComponentType, ReactNode, SVGProps } from "react";

  export interface GeographyObject {
    rsmKey: string;
    properties?: Record<string, unknown>;
    [key: string]: unknown;
  }

  export interface ZoomableGroupMoveEnd {
    coordinates: [number, number];
    zoom: number;
  }

  export const ComposableMap: ComponentType<SVGProps<SVGSVGElement> & {
    projection?: string;
    projectionConfig?: Record<string, unknown>;
    children?: ReactNode;
  }>;

  export const Geographies: ComponentType<{
    geography: string | Record<string, unknown>;
    children: (args: { geographies: GeographyObject[] }) => ReactNode;
  }>;

  export const Geography: ComponentType<SVGProps<SVGPathElement> & {
    geography: GeographyObject;
    style?: Record<string, Record<string, string>>;
  }>;

  export const Marker: ComponentType<SVGProps<SVGGElement> & {
    coordinates: [number, number];
    children?: ReactNode;
  }>;

  export const ZoomableGroup: ComponentType<{
    center?: [number, number];
    zoom?: number;
    onMoveEnd?: (position: ZoomableGroupMoveEnd) => void;
    children?: ReactNode;
  }>;
}
