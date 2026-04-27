{{/*
Juniper Helm chart — shared template helpers.
*/}}

{{/*
Chart name, truncated to 63 chars.
*/}}
{{- define "juniper.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Release-qualified fullname: <release>-juniper, truncated to 63 chars.
*/}}
{{- define "juniper.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Chart label value: <name>-<version>.
*/}}
{{- define "juniper.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "juniper.labels" -}}
helm.sh/chart: {{ include "juniper.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: juniper
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Selector labels (subset used in matchLabels).
Usage: include "juniper.selectorLabels" (dict "ctx" . "component" "data")
*/}}
{{- define "juniper.selectorLabels" -}}
app.kubernetes.io/name: {{ include "juniper.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/* ── Per-service fullnames ────────────────────────────────────────── */}}

{{- define "juniper.data.fullname" -}}
{{- printf "%s-data" (include "juniper.fullname" .) }}
{{- end }}

{{- define "juniper.cascor.fullname" -}}
{{- printf "%s-cascor" (include "juniper.fullname" .) }}
{{- end }}

{{- define "juniper.canopy.fullname" -}}
{{- printf "%s-canopy" (include "juniper.fullname" .) }}
{{- end }}

{{- define "juniper.worker.fullname" -}}
{{- printf "%s-worker" (include "juniper.fullname" .) }}
{{- end }}

{{/* ── Secret name ──────────────────────────────────────────────────── */}}

{{/*
Resolves to the user-provided existingSecret or the chart-created secret name.
*/}}
{{- define "juniper.secretName" -}}
{{- if .Values.secrets.existingSecret }}
{{- .Values.secrets.existingSecret }}
{{- else }}
{{- include "juniper.fullname" . }}
{{- end }}
{{- end }}

{{/* ── Computed service URLs ─────────────────────────────────────────── */}}

{{- define "juniper.data.serviceUrl" -}}
http://{{ include "juniper.data.fullname" . }}:{{ .Values.data.service.port }}
{{- end }}

{{- define "juniper.cascor.serviceUrl" -}}
http://{{ include "juniper.cascor.fullname" . }}:{{ .Values.cascor.service.port }}
{{- end }}

{{- define "juniper.cascor.wsUrl" -}}
ws://{{ include "juniper.cascor.fullname" . }}:{{ .Values.cascor.service.port }}/ws/v1/workers
{{- end }}

{{- define "juniper.redis.url" -}}
{{- if and .Values.redis.auth.enabled .Values.redis.auth.password -}}
redis://:{{ .Values.redis.auth.password }}@{{ .Release.Name }}-redis-master:6379/0
{{- else -}}
redis://{{ .Release.Name }}-redis-master:6379/0
{{- end -}}
{{- end }}

{{/* ── Pod security context ──────────────────────────────────────────── */}}

{{- define "juniper.podSecurityContext" -}}
runAsNonRoot: {{ .Values.securityContext.runAsNonRoot }}
runAsUser: {{ .Values.securityContext.runAsUser }}
runAsGroup: {{ .Values.securityContext.runAsGroup }}
fsGroup: {{ .Values.securityContext.fsGroup }}
{{- end }}

{{- define "juniper.containerSecurityContext" -}}
readOnlyRootFilesystem: {{ .Values.securityContext.readOnlyRootFilesystem }}
allowPrivilegeEscalation: {{ .Values.securityContext.allowPrivilegeEscalation }}
capabilities:
  drop:
    {{- toYaml .Values.securityContext.capabilities.drop | nindent 4 }}
{{- end }}

{{/* ── Image reference ───────────────────────────────────────────────── */}}

{{/*
Builds a fully-qualified image reference.
Usage: include "juniper.image" (dict "image" .Values.data.image "global" .Values.global)
*/}}
{{- define "juniper.image" -}}
{{- $registry := .image.registry | default .global.imageRegistry | default "" -}}
{{- if $registry }}
{{- printf "%s/%s:%s" $registry .image.repository (.image.tag | default "latest") }}
{{- else }}
{{- printf "%s:%s" .image.repository (.image.tag | default "latest") }}
{{- end }}
{{- end }}
