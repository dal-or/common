export type TipoDocumento = 'factura' | 'comprobante';

export interface Servicio {
  id: number;
  nombre: string;
}

export interface Documento {
  id: number;
  servicio_id: number;
  servicio_nombre?: string;
  anio: number;
  mes: number;
  tipo: TipoDocumento;
  nombre_archivo: string;
  ruta_archivo: string;
  monto: number | null;
  fecha_subida: string;
}

export interface EstadoServicio {
  servicio: Servicio;
  factura: Documento | null;
  comprobante: Documento | null;
}
