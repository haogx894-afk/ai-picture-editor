import type { Asset } from '@/api/assets'

export default function MicroThumbnail({
  asset,
  active,
  disabled,
  onClick,
  title,
  label,
}: {
  asset: Asset
  active: boolean
  disabled: boolean
  onClick: () => void
  title: string
  label: string
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      title={title}
      aria-pressed={active}
      className={`micro-thumbnail ${active ? 'micro-thumbnail--active' : ''}`}
    >
      <span className="micro-thumbnail__frame">
        <img
          src={asset.url}
          alt=""
          width={asset.width}
          height={asset.height}
          loading="lazy"
        />
        <span className="micro-thumbnail__slats" aria-hidden="true" />
        <span className="micro-thumbnail__label">{label}</span>
      </span>
    </button>
  )
}
